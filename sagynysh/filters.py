"""Pure decision logic for whether a message is worth learning from. No
Telegram dependency — callers pass in booleans extracted from wherever the
message came from (a live update or a chat export), so this is reusable by
both the live learn handler and the export training tool."""

from __future__ import annotations

from sagynysh import tokenizer

MIN_TOKENS = 1
MAX_TOKENS = 60


def should_learn(
    text: str,
    *,
    is_bot: bool,
    is_forwarded: bool,
    bot_username: str | None = None,
) -> bool:
    if is_bot or is_forwarded:
        return False

    stripped = text.strip()
    if not stripped or stripped.startswith("/"):
        return False

    raw_tokens = stripped.split()
    if all(tokenizer.is_url(t) for t in raw_tokens):
        return False

    tokens = tokenizer.tokenize(stripped, bot_username=bot_username)
    return MIN_TOKENS <= len(tokens) <= MAX_TOKENS
