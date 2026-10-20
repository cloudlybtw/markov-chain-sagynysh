"""Passive learning: learn from every eligible text/photo message. Always
raises SkipHandler so handlers/reply.py still gets a chance at the same
message afterward."""

from __future__ import annotations

import logging

import aiosqlite
from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from sagynysh import db, filters, markov
from sagynysh.config import Config

logger = logging.getLogger(__name__)

router = Router(name="learn")
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


def _is_bot_sender(message: Message) -> bool:
    return bool(message.from_user and message.from_user.is_bot)


def _is_forwarded(message: Message) -> bool:
    return message.forward_origin is not None


@router.message(F.photo)
async def learn_photo(
    message: Message,
    config: Config,
    conn: aiosqlite.Connection,
    bot_username: str = "",
) -> None:
    photo = message.photo[-1]
    await db.add_photo(conn, message.chat.id, photo.file_id)
    logger.info("chat_id=%s: saved photo", message.chat.id)

    caption = message.caption
    is_bot = _is_bot_sender(message)
    is_forwarded = _is_forwarded(message)
    if caption and filters.should_learn(
        caption, is_bot=is_bot, is_forwarded=is_forwarded, bot_username=bot_username
    ):
        settings = await db.get_chat_settings(conn, message.chat.id, config)
        await markov.learn(
            conn, message.chat.id, caption, settings.markov_order, bot_username=bot_username
        )
        logger.info("chat_id=%s: learned photo caption", message.chat.id)

    raise SkipHandler


@router.message(F.text)
async def learn_text(
    message: Message,
    config: Config,
    conn: aiosqlite.Connection,
    bot_username: str = "",
) -> None:
    text = message.text or ""
    is_bot = _is_bot_sender(message)
    is_forwarded = _is_forwarded(message)
    if filters.should_learn(
        text, is_bot=is_bot, is_forwarded=is_forwarded, bot_username=bot_username
    ):
        settings = await db.get_chat_settings(conn, message.chat.id, config)
        await markov.learn(
            conn, message.chat.id, text, settings.markov_order, bot_username=bot_username
        )
        logger.info("chat_id=%s: learned text message", message.chat.id)

    raise SkipHandler
