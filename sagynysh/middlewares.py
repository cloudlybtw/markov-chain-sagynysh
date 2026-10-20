"""Aiogram middlewares. Keeps the bot private to the configured friend group."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Chat, TelegramObject

logger = logging.getLogger(__name__)


class AllowedChatsMiddleware(BaseMiddleware):
    """If ALLOWED_CHAT_IDS is set, silently drop and leave any group chat
    that isn't on the list. An empty allowlist means every chat is allowed."""

    def __init__(self, allowed_chat_ids: frozenset[int]) -> None:
        self.allowed_chat_ids = allowed_chat_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat: Chat | None = data.get("event_chat")
        if (
            self.allowed_chat_ids
            and chat is not None
            and chat.type in ("group", "supergroup")
            and chat.id not in self.allowed_chat_ids
        ):
            logger.info("leaving disallowed chat_id=%s", chat.id)
            await data["bot"].leave_chat(chat.id)
            return None

        return await handler(event, data)
