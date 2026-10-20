"""Read Telegram Desktop HTML exports without importing layout or media metadata."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

_PAGE_NAME = re.compile(r"messages(\d*)\.html", re.IGNORECASE)


class _ExportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.messages: list[dict[str, Any]] = []
        self._depth = 0
        self._message_depth: int | None = None
        self._text_depth: int | None = None
        self._message: dict[str, Any] | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "div":
            self._depth += 1
            if "message" in classes and self._message is None:
                # Date separators have no ID and are not actual messages.
                message_id = attributes.get("id")
                if message_id:
                    self._message = {
                        "id": message_id,
                        "type": "service" if "service" in classes else "message",
                        "text": "",
                    }
                    self._message_depth = self._depth
            elif self._message is not None:
                if "forwarded_from" in classes or "forwarded" in classes:
                    self._message["forwarded_from"] = True
                if "text" in classes and self._text_depth is None:
                    self._text_depth = self._depth
                    self._parts = []
        elif self._text_depth is not None:
            if tag == "br":
                self._parts.append("\n")
            elif tag == "img":
                # Some exports represent emoji as images inside message text.
                self._parts.append(attributes.get("alt") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag != "div":
            return
        if self._text_depth == self._depth and self._message is not None:
            self._message["text"] += "".join(self._parts).strip()
            self._text_depth = None
        if self._message_depth == self._depth and self._message is not None:
            self.messages.append(self._message)
            self._message = None
            self._message_depth = None
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._text_depth is not None:
            self._parts.append(data)


def read_html_export(path: Path) -> dict[str, Any]:
    """Read one HTML page, or every messages*.html page in an export folder.

    Normalize to the JSON trainer's message shape. IDs are deduplicated across
    pages, but identical text in separate messages is deliberately preserved.
    """
    if path.is_dir():
        numbered_pages = [
            (int(match[1] or "1"), page)
            for page in path.iterdir()
            if page.is_file() and (match := _PAGE_NAME.fullmatch(page.name))
        ]
        pages = [page for _, page in sorted(numbered_pages)]
        if not pages:
            raise ValueError("В папке нет страниц messages*.html")
    else:
        pages = [path]

    messages: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for page in pages:
        parser = _ExportParser()
        parser.feed(page.read_text(encoding="utf-8-sig"))
        parser.close()
        for message in parser.messages:
            if message["id"] not in seen_ids:
                messages.append(message)
                seen_ids.add(message["id"])
    if not messages:
        raise ValueError("В HTML не найдены сообщения экспорта Telegram")
    return {"messages": messages}
