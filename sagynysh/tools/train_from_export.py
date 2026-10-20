"""CLI: pre-train a chat from a Telegram Desktop JSON or HTML export,
so the bot is funny from day one.

Usage:
    python -m sagynysh.tools.train_from_export result.json --chat-id -1001234567890
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import aiosqlite

from sagynysh import db, filters, markov
from sagynysh.tools.html_export import read_html_export

logger = logging.getLogger(__name__)

DEFAULT_ORDER = 1
DEFAULT_DB_PATH = "data/sagynysh.db"


def _extract_text(raw: str | list[Any]) -> str:
    """Telegram Desktop's `text` field is either a plain string, or a list
    mixing plain strings and entity dicts like {"type": "bold", "text": "..."}."""
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, list):
        return ""

    parts: list[str] = []
    for item in raw:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(str(item.get("text", "")))
    return "".join(parts)


def iter_learnable_texts(export: dict[str, Any]) -> list[str]:
    """Pick out the message texts worth learning from a parsed export.

    Bot authorship can't be reliably detected from the export format, so
    is_bot is always treated as False here — forwards, commands, link-only
    and over/under-length messages are still filtered out.
    """
    texts: list[str] = []
    for message in export.get("messages", []):
        if message.get("type") != "message":
            continue  # skip service messages: joins, pins, calls, ...

        text = _extract_text(message.get("text", ""))
        is_forwarded = "forwarded_from" in message
        if filters.should_learn(text, is_bot=False, is_forwarded=is_forwarded):
            texts.append(text)

    return texts


async def learn_export(
    conn: aiosqlite.Connection, export: dict[str, Any], chat_id: int, order: int
) -> tuple[int, int]:
    """Learn every eligible message from a parsed export.

    Returns (learned, skipped).
    """
    total = len(export.get("messages", []))
    texts = iter_learnable_texts(export)

    for text in texts:
        await markov.learn(conn, chat_id, text, order)

    return len(texts), total - len(texts)


async def train_from_file(
    export_path: Path, chat_id: int, order: int, db_path: str
) -> tuple[int, int]:
    if export_path.is_dir() or export_path.suffix.lower() in {".html", ".htm"}:
        export = read_html_export(export_path)
    else:
        export = json.loads(export_path.read_text(encoding="utf-8"))

    conn = await db.connect(db_path)
    try:
        return await learn_export(conn, export, chat_id, order)
    finally:
        await conn.close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-train a chat from a Telegram Desktop JSON or HTML export."
    )
    parser.add_argument(
        "export_path", type=Path, help="Path to result.json, an HTML page, or an HTML export folder"
    )
    parser.add_argument("--chat-id", type=int, required=True, help="Chat ID to train into")
    parser.add_argument(
        "--order", type=int, default=DEFAULT_ORDER, help=f"Markov order (default: {DEFAULT_ORDER})"
    )
    parser.add_argument(
        "--db-path", type=str, default=DEFAULT_DB_PATH, help=f"DB path (default: {DEFAULT_DB_PATH})"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args(argv)

    learned, skipped = asyncio.run(
        train_from_file(args.export_path, args.chat_id, args.order, args.db_path)
    )
    logger.info("chat_id=%d: learned %d messages, skipped %d", args.chat_id, learned, skipped)


if __name__ == "__main__":
    main()
