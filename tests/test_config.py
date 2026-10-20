import os
from pathlib import Path

import pytest

from sagynysh.config import load_config


def test_load_config_defaults():
    config = load_config(env={"BOT_TOKEN": "123:abc"})

    assert config.bot_token == "123:abc"
    assert config.db_path == "data/sagynysh.db"
    assert config.default_chance == 10
    assert config.direct_reply_chance == 10
    assert config.meme_chance == 5
    assert config.demotivator_chance == 5
    assert config.markov_order == 1
    assert config.max_words == 25
    assert config.allowed_chat_ids == frozenset()
    assert config.admin_user_ids == frozenset()


def test_load_config_parses_overrides_and_id_lists():
    config = load_config(
        env={
            "BOT_TOKEN": "123:abc",
            "DB_PATH": "custom.db",
            "DEFAULT_CHANCE": "42",
            "MARKOV_ORDER": "2",
            "MAX_WORDS": "10",
            "ALLOWED_CHAT_IDS": "-100111, -100222",
            "ADMIN_USER_IDS": "111,222",
        }
    )

    assert config.db_path == "custom.db"
    assert config.default_chance == 42
    assert config.markov_order == 2
    assert config.max_words == 10
    assert config.allowed_chat_ids == frozenset({-100111, -100222})
    assert config.admin_user_ids == frozenset({111, 222})


def test_load_config_missing_bot_token_raises():
    with pytest.raises(ValueError):
        load_config(env={})


def test_load_config_blank_id_lists_are_empty_set():
    config = load_config(env={"BOT_TOKEN": "x", "ALLOWED_CHAT_IDS": "", "ADMIN_USER_IDS": ""})

    assert config.allowed_chat_ids == frozenset()
    assert config.admin_user_ids == frozenset()


@pytest.mark.parametrize("legacy_comments", [False, True])
def test_load_config_from_dotenv_with_optional_blank_settings(
    tmp_path, monkeypatch, legacy_comments
):
    example_path = Path(__file__).parents[1] / ".env.example"
    contents = example_path.read_text().replace("BOT_TOKEN=", "BOT_TOKEN=123:abc", 1)
    if legacy_comments:
        contents = contents.replace(
            "ALLOWED_CHAT_IDS=", "ALLOWED_CHAT_IDS=    # optional whitelist; empty = any chat"
        ).replace("ADMIN_USER_IDS=", "ADMIN_USER_IDS=    # optional admins")
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(contents)
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for name in (
        "BOT_TOKEN",
        "DB_PATH",
        "DEFAULT_CHANCE",
        "COMMON_REPLY_CHANCE",
        "DIRECT_REPLY_CHANCE",
        "MEME_CHANCE",
        "DEMOTIVATOR_CHANCE",
        "MARKOV_ORDER",
        "MAX_WORDS",
        "ALLOWED_CHAT_IDS",
        "ADMIN_USER_IDS",
    ):
        monkeypatch.delenv(name, raising=False)
    # Isolate load_dotenv's environment writes from other tests.
    config = load_config(dotenv_path=str(dotenv_path))

    assert config.bot_token == "123:abc"
    assert config.allowed_chat_ids == frozenset()
    assert config.admin_user_ids == frozenset()


def test_load_config_rejects_comment_only_bot_token():
    with pytest.raises(ValueError, match="BOT_TOKEN is required"):
        load_config(env={"BOT_TOKEN": "# from @BotFather"})


def test_load_config_still_rejects_invalid_id_lists():
    with pytest.raises(ValueError):
        load_config(env={"BOT_TOKEN": "123:abc", "ALLOWED_CHAT_IDS": "-100111,invalid"})


def test_independent_env_chances_and_legacy_alias():
    config = load_config(
        env={
            "BOT_TOKEN": "x",
            "DEFAULT_CHANCE": "99",
            "COMMON_REPLY_CHANCE": "12",
            "DIRECT_REPLY_CHANCE": "34",
            "MEME_CHANCE": "20",
            "DEMOTIVATOR_CHANCE": "30",
            "MARKOV_ORDER": "5",
        }
    )
    assert config.default_chance == 12
    assert config.direct_reply_chance == 34
    assert config.meme_chance == 20
    assert config.demotivator_chance == 30
    assert config.markov_order == 5


@pytest.mark.parametrize(
    "name,value",
    [
        ("COMMON_REPLY_CHANCE", "101"),
        ("DIRECT_REPLY_CHANCE", "-1"),
        ("MEME_CHANCE", "101"),
        ("DEMOTIVATOR_CHANCE", "-1"),
        ("MARKOV_ORDER", "0"),
        ("MARKOV_ORDER", "6"),
        ("MAX_WORDS", "0"),
    ],
)
def test_invalid_env_ranges(name, value):
    with pytest.raises(ValueError, match=name):
        load_config(env={"BOT_TOKEN": "x", name: value})


def test_invalid_env_media_total():
    with pytest.raises(ValueError, match="must not exceed 100"):
        load_config(env={"BOT_TOKEN": "x", "MEME_CHANCE": "60", "DEMOTIVATOR_CHANCE": "41"})
