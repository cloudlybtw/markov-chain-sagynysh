import json

from sagynysh import db
from sagynysh.tools import train_from_export as tfe


def _msg(text, msg_type="message", **extra):
    return {"id": 1, "type": msg_type, "date": "2024-01-01T00:00:00", "text": text, **extra}


def test_extract_text_handles_plain_string():
    assert tfe._extract_text("привет мир") == "привет мир"


def test_extract_text_handles_list_of_strings_and_entities():
    raw = [
        "смотри ",
        {"type": "bold", "text": "жирный текст"},
        " и ",
        {"type": "text_link", "text": "ссылку", "href": "https://example.com"},
    ]
    assert tfe._extract_text(raw) == "смотри жирный текст и ссылку"


def test_extract_text_handles_empty_list():
    assert tfe._extract_text([]) == ""


def test_iter_learnable_texts_skips_service_messages():
    export = {
        "messages": [
            _msg("кто-то присоединился", msg_type="service", action="join"),
            _msg("привет всем как дела сегодня"),
        ]
    }
    assert tfe.iter_learnable_texts(export) == ["привет всем как дела сегодня"]


def test_iter_learnable_texts_skips_forwarded_messages():
    export = {
        "messages": [
            _msg("привет всем как дела сегодня", forwarded_from="Кто-то"),
            _msg("это не переслано а нормальное сообщение"),
        ]
    }
    assert tfe.iter_learnable_texts(export) == ["это не переслано а нормальное сообщение"]


def test_iter_learnable_texts_skips_commands_and_link_only():
    export = {
        "messages": [
            _msg("/start"),
            _msg("https://example.com/path"),
            _msg("нормальное сообщение с текстом"),
        ]
    }
    assert tfe.iter_learnable_texts(export) == ["нормальное сообщение с текстом"]


def test_iter_learnable_texts_handles_entity_list_text():
    export = {
        "messages": [
            _msg([{"type": "bold", "text": "привет"}, " всем сегодня"]),
        ]
    }
    assert tfe.iter_learnable_texts(export) == ["привет всем сегодня"]


async def test_learn_export_learns_only_eligible_messages_and_reports_counts(conn):
    export = {
        "messages": [
            _msg("кот сидит дома"),
            _msg("кот спит тихо"),
            _msg("/start"),
            _msg("присоединился к чату", msg_type="service"),
            _msg("собака бежит быстро", forwarded_from="Кто-то"),
        ]
    }

    learned, skipped = await tfe.learn_export(conn, export, chat_id=1, order=1)

    assert learned == 2
    assert skipped == 3

    stats = await db.get_stats(conn, chat_id=1)
    assert stats["messages_learned"] == 2


async def test_train_from_file_reads_json_and_learns(tmp_path):
    export = {
        "messages": [_msg("кот сидит дома"), _msg("кот спит тихо")],
    }
    export_path = tmp_path / "result.json"
    export_path.write_text(json.dumps(export), encoding="utf-8")

    learned, skipped = await tfe.train_from_file(
        export_path, chat_id=42, order=1, db_path=":memory:"
    )

    assert learned == 2
    assert skipped == 0
