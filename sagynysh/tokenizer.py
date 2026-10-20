"""Text <-> tokens conversion, plus the START/END sequence padding used by
the Markov engine. No Telegram dependency — pure string logic."""

from __future__ import annotations

import re
import string
from collections.abc import Iterable

START = "__START__"
END = "__END__"
CONTEXT_SEP = "\x1f"
MAX_TOKEN_LENGTH = 40

_URL_RE = re.compile(r"^(https?://|www\.)\S+", re.IGNORECASE)
_TRIM_CHARS = string.punctuation + "«»…„“”‘’—–"


def is_url(token: str) -> bool:
    return bool(_URL_RE.match(token))


def _is_self_mention(token: str, bot_username: str | None) -> bool:
    if not bot_username or not token.startswith("@"):
        return False
    handle = token[1:].strip(_TRIM_CHARS).lower()
    return handle == bot_username.lstrip("@").lower()


def tokenize(text: str, bot_username: str | None = None) -> list[str]:
    """Split on whitespace, keeping punctuation attached to words and
    original casing. Drops URLs, self-mentions and overlong tokens."""
    tokens: list[str] = []
    for raw in text.split():
        if is_url(raw):
            continue
        if _is_self_mention(raw, bot_username):
            continue
        if len(raw) > MAX_TOKEN_LENGTH:
            continue
        tokens.append(raw)
    return tokens


def detokenize(tokens: Iterable[str]) -> str:
    return " ".join(tokens)


def cap_words(text: str, max_words: int) -> str:
    return " ".join(text.split()[:max_words])


def build_sequence(tokens: list[str], order: int) -> list[str]:
    """[START]*order + tokens + [END], as learned by the Markov engine."""
    return [START] * order + list(tokens) + [END]
