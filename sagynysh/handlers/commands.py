"""Slash commands. /start and /help work everywhere (including DMs); every
other command is group/supergroup-only."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiosqlite
from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    User,
)
from PIL import Image

from sagynysh import db, images, markov, texts, tokenizer
from sagynysh.config import MAX_MARKOV_ORDER, Config

logger = logging.getLogger(__name__)

CAPTION_MAX_WORDS = 8

BOT_COMMANDS = [
    BotCommand(command="help", description="Что я умею"),
    BotCommand(command="say", description="Сгенерировать сообщение"),
    BotCommand(command="admin_only", description="Все команды только админам: on/off"),
    BotCommand(command="chance", description="Показать/задать шанс ответа"),
    BotCommand(command="direct_chance", description="Шанс ответа на реплай боту (админ)"),
    BotCommand(command="markov_order", description="Порядок цепи Маркова (админ)"),
    BotCommand(command="meme_chance", description="Доля мемов в случайных ответах (админ)"),
    BotCommand(command="demotivator_chance", description="Доля демотиваторов (админ)"),
    BotCommand(command="demotivator", description="Демотиватор из случайного фото"),
    BotCommand(command="meme", description="Мем из случайного фото"),
    BotCommand(command="stats", description="Статистика по чату"),
    BotCommand(command="forget", description="Забыть всё, что я выучил"),
]

help_router = Router(name="commands_help")


@help_router.message(Command("start", "help"))
async def cmd_help(message: Message) -> None:
    await message.reply(texts.HELP)


router = Router(name="commands")
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


async def _is_admin(bot: Bot, chat_id: int, user: User | None, config: Config) -> bool:
    if user is None or user.is_bot:
        return False
    if user.id in config.admin_user_ids:
        return True
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except TelegramAPIError:
        logger.warning("chat_id=%s: could not verify chat administrators", chat_id)
        return False
    return any(admin.user.id == user.id for admin in admins)


async def _message_is_admin(message: Message, config: Config) -> bool:
    if message.sender_chat is not None:
        # Telegram identifies anonymous group admins by the group's sender_chat.
        return message.sender_chat.id == message.chat.id
    return await _is_admin(message.bot, message.chat.id, message.from_user, config)


class AdminOnlyCommandsMiddleware(BaseMiddleware):
    """Gate every matched group command, including aliases and /start or /help.

    Inner middleware belongs only to the command routers, so passive learning
    and automatic replies are unaffected. Private /help keeps its existing access.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if (
            event.chat.type in {"group", "supergroup"}
            and await db.get_admin_only(data["conn"], event.chat.id)
            and not await _message_is_admin(event, data["config"])
        ):
            await event.reply(texts.CHANCE_NOT_ADMIN)
            return None
        return await handler(event, data)


help_router.message.middleware(AdminOnlyCommandsMiddleware())
router.message.middleware(AdminOnlyCommandsMiddleware())


@router.message(Command("admin_only"))
async def cmd_admin_only(
    message: Message, command: CommandObject, config: Config, conn: aiosqlite.Connection
) -> None:
    if not await _message_is_admin(message, config):
        await message.reply(texts.CHANCE_NOT_ADMIN)
        return
    if command.args is None:
        enabled = await db.get_admin_only(conn, message.chat.id)
    else:
        value = command.args.strip().lower()
        if value not in {"on", "off"}:
            await message.reply(texts.ADMIN_ONLY_USAGE)
            return
        enabled = value == "on"
        await db.set_admin_only(conn, message.chat.id, enabled)
    await message.reply(texts.ADMIN_ONLY_STATUS.format(state="on" if enabled else "off"))


@router.message(Command("say"))
async def cmd_say(message: Message, config: Config, conn: aiosqlite.Connection) -> None:
    settings = await db.get_chat_settings(conn, message.chat.id, config)
    text = await markov.generate(conn, message.chat.id, settings.markov_order, config.max_words)
    await message.reply(text if text else texts.NO_DATA)


@router.message(Command("chance", "common_chance", "common_reply_chance"))
async def cmd_chance(
    message: Message,
    command: CommandObject,
    config: Config,
    conn: aiosqlite.Connection,
) -> None:
    await _setting_command(message, command, config, conn, "common_reply_chance")


@router.message(Command("direct_chance", "direct_reply_chance"))
async def cmd_direct_chance(
    message: Message, command: CommandObject, config: Config, conn: aiosqlite.Connection
) -> None:
    await _setting_command(message, command, config, conn, "direct_reply_chance")


@router.message(Command("markov_order"))
async def cmd_markov_order(
    message: Message, command: CommandObject, config: Config, conn: aiosqlite.Connection
) -> None:
    await _setting_command(message, command, config, conn, "markov_order")


@router.message(Command("meme_chance"))
async def cmd_meme_chance(
    message: Message, command: CommandObject, config: Config, conn: aiosqlite.Connection
) -> None:
    await _setting_command(message, command, config, conn, "meme_chance")


@router.message(Command("demotivator_chance"))
async def cmd_demotivator_chance(
    message: Message, command: CommandObject, config: Config, conn: aiosqlite.Connection
) -> None:
    await _setting_command(message, command, config, conn, "demotivator_chance")


async def _setting_command(
    message: Message,
    command: CommandObject,
    config: Config,
    conn: aiosqlite.Connection,
    name: str,
) -> None:
    if not await _message_is_admin(message, config):
        await message.reply(texts.CHANCE_NOT_ADMIN)
        return
    settings = await db.get_chat_settings(conn, message.chat.id, config)
    label = texts.SETTING_NAMES[name]
    unit = "" if name == "markov_order" else "%"
    if not command.args:
        await message.reply(
            texts.SETTING_SHOW.format(label=label, value=getattr(settings, name), unit=unit)
        )
        return
    low, high = (1, MAX_MARKOV_ORDER) if name == "markov_order" else (0, 100)
    try:
        value = int(command.args.strip())
    except ValueError:
        value = -1
    if not low <= value <= high:
        await message.reply(texts.SETTING_INVALID.format(low=low, high=high))
        return
    try:
        await db.set_chat_setting(conn, message.chat.id, config, name, value)
    except ValueError:
        await message.reply(texts.MEDIA_CHANCE_INVALID)
        return
    await message.reply(texts.SETTING_SET.format(label=label, value=value, unit=unit))


@router.message(Command("stats"))
async def cmd_stats(message: Message, conn: aiosqlite.Connection) -> None:
    stats = await db.get_stats(conn, message.chat.id)
    await message.reply(texts.STATS.format(chat_id=message.chat.id, **stats))


async def _resolve_photo_file_id(message: Message, conn: aiosqlite.Connection) -> str | None:
    reply_to = message.reply_to_message
    if reply_to and reply_to.photo:
        return reply_to.photo[-1].file_id
    return await db.random_photo(conn, message.chat.id)


async def _generate_caption(message: Message, config: Config, conn: aiosqlite.Connection) -> str:
    settings = await db.get_chat_settings(conn, message.chat.id, config)
    text = await markov.generate(conn, message.chat.id, settings.markov_order, config.max_words)
    return tokenizer.cap_words(text, CAPTION_MAX_WORDS) if text else ""


async def send_demotivator(
    message: Message,
    config: Config,
    conn: aiosqlite.Connection,
    file_id: str,
    *,
    as_reply: bool = True,
) -> None:
    title = await _generate_caption(message, config, conn)
    subtitle = await _generate_caption(message, config, conn)

    photo_bytes = await message.bot.download(file_id)
    photo = Image.open(photo_bytes)
    jpeg_bytes = await asyncio.to_thread(images.render_demotivator, photo, title, subtitle)
    input_file = BufferedInputFile(jpeg_bytes, filename="demotivator.jpg")

    if as_reply:
        await message.reply_photo(input_file)
    else:
        await message.answer_photo(input_file)


async def send_meme(
    message: Message,
    config: Config,
    conn: aiosqlite.Connection,
    file_id: str,
    *,
    as_reply: bool = True,
) -> None:
    top = await _generate_caption(message, config, conn)
    bottom = await _generate_caption(message, config, conn)

    photo_bytes = await message.bot.download(file_id)
    photo = Image.open(photo_bytes)
    jpeg_bytes = await asyncio.to_thread(images.render_meme, photo, top, bottom)
    input_file = BufferedInputFile(jpeg_bytes, filename="meme.jpg")

    if as_reply:
        await message.reply_photo(input_file)
    else:
        await message.answer_photo(input_file)


@router.message(Command("demotivator"))
async def cmd_demotivator(message: Message, config: Config, conn: aiosqlite.Connection) -> None:
    file_id = await _resolve_photo_file_id(message, conn)
    if not file_id:
        await message.reply(texts.NO_PHOTOS)
        return
    await send_demotivator(message, config, conn, file_id)


@router.message(Command("meme"))
async def cmd_meme(message: Message, config: Config, conn: aiosqlite.Connection) -> None:
    file_id = await _resolve_photo_file_id(message, conn)
    if not file_id:
        await message.reply(texts.NO_PHOTOS)
        return
    await send_meme(message, config, conn, file_id)


@router.message(Command("forget"))
async def cmd_forget(message: Message, config: Config) -> None:
    if not await _message_is_admin(message, config):
        await message.reply(texts.FORGET_NOT_ADMIN)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.FORGET_BUTTON_YES, callback_data="forget:yes"),
                InlineKeyboardButton(text=texts.FORGET_BUTTON_NO, callback_data="forget:no"),
            ]
        ]
    )
    await message.reply(texts.FORGET_CONFIRM, reply_markup=keyboard)


@router.callback_query(F.data.in_({"forget:yes", "forget:no"}))
async def cb_forget(callback: CallbackQuery, config: Config, conn: aiosqlite.Connection) -> None:
    message = callback.message
    if message is None or message.chat.type not in {"group", "supergroup"}:
        await callback.answer()
        return
    if not await _is_admin(callback.bot, message.chat.id, callback.from_user, config):
        await callback.answer(texts.FORGET_NOT_ADMIN, show_alert=True)
        return

    async def _respond(text: str) -> None:
        # the original message may be an InaccessibleMessage (too old to edit)
        if hasattr(message, "edit_text"):
            await message.edit_text(text)
        else:
            await callback.bot.send_message(message.chat.id, text)

    if callback.data == "forget:no":
        await _respond(texts.FORGET_CANCELLED)
        await callback.answer()
        return

    await db.forget_chat(conn, message.chat.id)
    await _respond(texts.FORGET_DONE)
    await callback.answer()
    logger.info("chat_id=%s: forgot everything", message.chat.id)
