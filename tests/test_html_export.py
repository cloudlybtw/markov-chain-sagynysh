from pathlib import Path

import pytest

from sagynysh import db
from sagynysh.tools.html_export import read_html_export
from sagynysh.tools.train_from_export import (
    iter_learnable_texts,
    learn_export,
    train_from_file,
)


def _message(message_id: int, body: str, classes: str = "default clearfix") -> str:
    return (
        f'<div class="message {classes}" id="message{message_id}">'
        f'<div class="body">{body}</div></div>'
    )


def _page(path: Path, content: str) -> Path:
    path.write_text(f'<html><body><div class="history">{content}</div></body></html>')
    return path


def test_html_preserves_text_captions_entities_and_inline_formatting(tmp_path):
    page = _page(
        tmp_path / "messages.html",
        '<div class="message service"><div>1 January 2026</div></div>'
        + _message(
            1,
            '<div class="from_name">Автор</div><div class="date">12:34</div>'
            '<div class="reply_to"><a>this message</a></div>'
            '<div class="text">\nСәлем, <b>әлем!</b><br>ә ғ қ ң ө ұ ү һ і &amp; '
            '<a href="https://example.com">слово</a><img alt="🙂" src="emoji.png">\n</div>'
            '<div class="reactions">❤ 3</div>'
            '<div class="webpage_preview"><div class="webpage_title">Preview</div></div>',
        )
        + _message(
            2,
            '<div class="media_wrap"><a>Photo</a><div class="status">800x600</div></div>'
            '<div class="text">подпись к фото</div>',
            classes="default clearfix joined",
        ),
    )

    assert iter_learnable_texts(read_html_export(page)) == [
        "Сәлем, әлем!\nә ғ қ ң ө ұ ү һ і & слово🙂",
        "подпись к фото",
    ]


def test_html_filters_forwards_services_commands_links_and_media_only(tmp_path):
    page = _page(
        tmp_path / "messages.html",
        _message(1, '<div class="text">присоединился</div>', classes="service")
        + _message(
            2,
            '<div class="forwarded_from details">Forwarded from someone</div>'
            '<div class="text">пересланный текст</div>',
        )
        + _message(
            3,
            '<div class="forwarded body"><div class="text">ещё пересылка</div></div>',
        )
        + _message(4, '<div class="text">/start</div>')
        + _message(
            5, '<div class="text"><a href="https://example.com">https://example.com</a></div>'
        )
        + _message(6, '<div class="media_wrap"><div class="title">Sticker</div></div>')
        + _message(7, '<div class="text">' + "слово " * 61 + "</div>")
        + _message(8, '<div class="text">нормальный текст</div>'),
    )
    export = read_html_export(page)

    assert len(export["messages"]) == 8
    assert iter_learnable_texts(export) == ["нормальный текст"]


def test_html_folder_imports_all_pages_in_numeric_order_and_deduplicates_ids(tmp_path):
    _page(tmp_path / "messages10.html", _message(10, '<div class="text">десять</div>'))
    _page(tmp_path / "messages2.html", _message(2, '<div class="text">два</div>'))
    _page(
        tmp_path / "messages.html",
        _message(1, '<div class="text">два</div>') + _message(2, '<div class="text">два</div>'),
    )
    _page(tmp_path / "unrelated.html", _message(100, '<div class="text">лишнее</div>'))
    (tmp_path / "messages3.html").mkdir()

    assert iter_learnable_texts(read_html_export(tmp_path)) == ["два", "два", "десять"]


def test_html_single_file_imports_only_that_page(tmp_path):
    page = _page(tmp_path / "messages.html", _message(1, '<div class="text">один</div>'))
    _page(tmp_path / "messages2.html", _message(2, '<div class="text">два</div>'))
    assert iter_learnable_texts(read_html_export(page)) == ["один"]


def test_html_rejects_empty_folders_and_non_export_html(tmp_path):
    with pytest.raises(ValueError, match="messages"):
        read_html_export(tmp_path)
    page = _page(tmp_path / "messages.html", "<div>nothing here</div>")
    with pytest.raises(ValueError, match="Telegram"):
        read_html_export(page)


@pytest.mark.parametrize("order", [1, 2])
async def test_html_learns_into_only_the_requested_chat(tmp_path, conn, order):
    page = _page(
        tmp_path / "messages.html",
        _message(1, '<div class="text">кот сидит дома</div>')
        + _message(2, '<div class="text">/help</div>'),
    )
    assert await learn_export(conn, read_html_export(page), chat_id=42, order=order) == (1, 1)
    assert (await db.get_stats(conn, 42))["messages_learned"] == 1
    assert (await db.get_stats(conn, 43))["messages_learned"] == 0
    assert await db.get_transitions(conn, 42, "\x1f".join(["__START__"] * order)) == [("кот", 1)]


@pytest.mark.parametrize("folder", [False, True])
async def test_trainer_accepts_html_files_and_folders(tmp_path, folder):
    page = _page(tmp_path / "messages.html", _message(1, '<div class="text">кот дома</div>'))
    assert await train_from_file(
        tmp_path if folder else page, chat_id=42, order=1, db_path=":memory:"
    ) == (1, 0)
