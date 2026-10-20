"""Random / mention / reply-to-bot responses. Runs after handlers/learn.py
for the same message."""

from __future__ import annotations

import asyncio
import logging
import random
import time

import aiosqlite
from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from sagynysh import db, markov
from sagynysh.config import Config
from sagynysh.handlers import commands

logger = logging.getLogger(__name__)

router = Router(name="reply")
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

BOT_DISPLAY_NAMES = ("сглыпа", "sagynysh")
RANDOM_REPLY_COOLDOWN_SECONDS = 10.0


def _mentions_bot(text: str, bot_username: str) -> bool:
    lowered = text.lower()
    if bot_username and f"@{bot_username.lower()}" in lowered:
        return True
    return any(name in lowered for name in BOT_DISPLAY_NAMES)


def _is_reply_to_bot(message: Message, bot_id: int) -> bool:
    reply_to = message.reply_to_message
    return bool(reply_to and reply_to.from_user and reply_to.from_user.id == bot_id)


@router.message()
async def maybe_reply(
    message: Message,
    config: Config,
    conn: aiosqlite.Connection,
    bot_username: str = "",
    bot_id: int = 0,
    rng: random.Random | None = None,
    cooldowns: dict[int, float] | None = None,
) -> None:
    rng = rng if rng is not None else random.Random()
    cooldowns = cooldowns if cooldowns is not None else {}

    text = message.text or message.caption or ""
    if text.startswith("/"):
        return

    mentioned = _mentions_bot(text, bot_username)
    triggered = mentioned or _is_reply_to_bot(message, bot_id)
    settings = await db.get_chat_settings(conn, message.chat.id, config)

    if not mentioned:
        chance = settings.direct_reply_chance if triggered else settings.common_reply_chance
        if rng.randint(1, 100) > chance:
            return

    if not triggered:
        last = cooldowns.get(message.chat.id, 0.0)
        if time.monotonic() - last < RANDOM_REPLY_COOLDOWN_SECONDS:
            return

        media_roll = rng.random() * 100
        if media_roll < settings.demotivator_chance + settings.meme_chance:
            file_id = await db.random_photo(conn, message.chat.id)
            stats = await db.get_stats(conn, message.chat.id)
            if file_id and stats["messages_learned"] >= markov.MIN_MESSAGES_LEARNED:
                await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
                await asyncio.sleep(rng.uniform(1, 3))
                if media_roll < settings.demotivator_chance:
                    await commands.send_demotivator(message, config, conn, file_id, as_reply=False)
                else:
                    await commands.send_meme(message, config, conn, file_id, as_reply=False)
                cooldowns[message.chat.id] = time.monotonic()
                logger.info("chat_id=%s: sent random image", message.chat.id)
                return

    seed = markov.pick_seed(text, rng) if text else None
    reply_text = await markov.generate(
        conn, message.chat.id, settings.markov_order, config.max_words, seed=seed, rng=rng
    )
    if not reply_text:
        return

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    await asyncio.sleep(rng.uniform(1, 3))

    if triggered:
        await message.reply(reply_text)
    else:
        await message.answer(reply_text)
        cooldowns[message.chat.id] = time.monotonic()

    logger.info(
        "chat_id=%s: sent %s reply", message.chat.id, "triggered" if triggered else "random"
    )
