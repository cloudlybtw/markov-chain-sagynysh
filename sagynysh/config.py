"""Loads environment variables into a frozen config object."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from dotenv import load_dotenv

MAX_MARKOV_ORDER = 5


@dataclass(frozen=True, slots=True)
class ChatSettings:
    markov_order: int
    common_reply_chance: int
    direct_reply_chance: int
    meme_chance: int
    demotivator_chance: int


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    db_path: str
    default_chance: int
    markov_order: int
    max_words: int
    allowed_chat_ids: frozenset[int]
    admin_user_ids: frozenset[int]
    direct_reply_chance: int
    meme_chance: int
    demotivator_chance: int


def _parse_id_set(value: str) -> frozenset[int]:
    # Older .env.example versions put a comment after a blank assignment.
    # python-dotenv returns that comment as the value rather than an empty string.
    if value.lstrip().startswith("#"):
        return frozenset()
    return frozenset(int(item) for item in value.split(",") if item.strip())


def load_config(env: Mapping[str, str] | None = None, dotenv_path: str | None = None) -> Config:
    """Build a Config. If `env` is given, read from it instead of the process
    environment (used by tests). Otherwise load `.env` via python-dotenv first.
    """
    if env is None:
        load_dotenv(dotenv_path)
        env = os.environ

    bot_token = env.get("BOT_TOKEN", "").strip()
    if not bot_token or bot_token.startswith("#"):
        raise ValueError("BOT_TOKEN is required (set it in .env)")

    common_chance = int(env.get("COMMON_REPLY_CHANCE", env.get("DEFAULT_CHANCE", "10")))
    config = Config(
        bot_token=bot_token,
        db_path=env.get("DB_PATH", "data/sagynysh.db"),
        default_chance=common_chance,
        markov_order=int(env.get("MARKOV_ORDER", "1")),
        max_words=int(env.get("MAX_WORDS", "25")),
        allowed_chat_ids=_parse_id_set(env.get("ALLOWED_CHAT_IDS", "")),
        admin_user_ids=_parse_id_set(env.get("ADMIN_USER_IDS", "")),
        direct_reply_chance=int(env.get("DIRECT_REPLY_CHANCE", str(common_chance))),
        meme_chance=int(env.get("MEME_CHANCE", "5")),
        demotivator_chance=int(env.get("DEMOTIVATOR_CHANCE", "5")),
    )
    for name, value in (
        ("COMMON_REPLY_CHANCE", config.default_chance),
        ("DIRECT_REPLY_CHANCE", config.direct_reply_chance),
        ("MEME_CHANCE", config.meme_chance),
        ("DEMOTIVATOR_CHANCE", config.demotivator_chance),
    ):
        if not 0 <= value <= 100:
            raise ValueError(f"{name} must be between 0 and 100")
    if config.meme_chance + config.demotivator_chance > 100:
        raise ValueError("MEME_CHANCE + DEMOTIVATOR_CHANCE must not exceed 100")
    if not 1 <= config.markov_order <= MAX_MARKOV_ORDER:
        raise ValueError(f"MARKOV_ORDER must be between 1 and {MAX_MARKOV_ORDER}")
    if config.max_words < 1:
        raise ValueError("MAX_WORDS must be positive")
    return config
