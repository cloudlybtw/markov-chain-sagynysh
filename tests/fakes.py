"""Lightweight test doubles for aiogram objects, shared across handler tests.
Handlers are plain async functions, so we call them directly with these
fakes instead of spinning up a real Dispatcher/Bot."""

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from PIL import Image

from sagynysh.config import Config, load_config


def make_downloaded_photo(width: int = 50, height: int = 50) -> io.BytesIO:
    """A small in-memory image, standing in for Bot.download()'s return value."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (100, 120, 140)).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def make_config(**overrides: Any) -> Config:
    env = {
        "BOT_TOKEN": "test-token",
        "DEFAULT_CHANCE": "10",
        "MARKOV_ORDER": "1",
        "MAX_WORDS": "25",
    }
    env.update({k: str(v) for k, v in overrides.items()})
    return load_config(env=env)


def make_user(user_id: int = 100, is_bot: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, is_bot=is_bot)


def make_chat(chat_id: int = 1, chat_type: str = "group") -> SimpleNamespace:
    return SimpleNamespace(id=chat_id, type=chat_type)


def make_photo(file_id: str = "photo1") -> SimpleNamespace:
    return SimpleNamespace(file_id=file_id)


def make_message(
    *,
    text: str | None = None,
    caption: str | None = None,
    chat_id: int = 1,
    from_user: SimpleNamespace | None = None,
    forward_origin: Any = None,
    reply_to_message: SimpleNamespace | None = None,
    photo: list[SimpleNamespace] | None = None,
    is_admin: bool = True,
    sender_chat: SimpleNamespace | None = None,
) -> SimpleNamespace:
    user = from_user if from_user is not None else make_user()
    bot = AsyncMock()
    bot.get_chat_administrators.return_value = [SimpleNamespace(user=user)] if is_admin else []
    return SimpleNamespace(
        text=text,
        caption=caption,
        chat=make_chat(chat_id),
        from_user=user,
        sender_chat=sender_chat,
        forward_origin=forward_origin,
        reply_to_message=reply_to_message,
        photo=photo,
        bot=bot,
        reply=AsyncMock(),
        answer=AsyncMock(),
        edit_text=AsyncMock(),
        reply_photo=AsyncMock(),
        answer_photo=AsyncMock(),
    )


class FakeRng:
    """Deterministic stand-in for random.Random with fixed return values,
    for tests that need to force a specific branch."""

    def __init__(
        self,
        randint_value: int = 100,
        random_value: float = 0.0,
        uniform_value: float = 1.0,
        choice_index: int = 0,
    ) -> None:
        self.randint_value = randint_value
        self.random_value = random_value
        self.uniform_value = uniform_value
        self.choice_index = choice_index

    def randint(self, a: int, b: int) -> int:
        return self.randint_value

    def random(self) -> float:
        return self.random_value

    def uniform(self, a: float, b: float) -> float:
        return self.uniform_value

    def choice(self, seq: list[Any]) -> Any:
        return seq[self.choice_index % len(seq)]

    def choices(
        self, population: list[Any], weights: list[Any] | None = None, k: int = 1
    ) -> list[Any]:
        return [population[self.choice_index % len(population)]] * k


def make_command(command: str = "chance", args: str | None = None):
    from aiogram.filters import CommandObject

    return CommandObject(prefix="/", command=command, args=args)


def make_callback(
    data: str,
    *,
    from_user: SimpleNamespace | None = None,
    message: SimpleNamespace | None = None,
    is_admin: bool = True,
) -> SimpleNamespace:
    user = from_user if from_user is not None else make_user()
    bot = AsyncMock()
    bot.get_chat_administrators.return_value = [SimpleNamespace(user=user)] if is_admin else []
    return SimpleNamespace(
        data=data,
        from_user=user,
        message=message if message is not None else make_message(),
        bot=bot,
        answer=AsyncMock(),
    )
