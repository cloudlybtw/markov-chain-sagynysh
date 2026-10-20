import pytest

from sagynysh import db, markov
from tests.fakes import make_config


async def test_get_or_create_chat_uses_default_then_persists(conn):
    chance = await db.get_or_create_chat(conn, chat_id=1, default_chance=10)
    assert chance == 10
    await db.set_chance(conn, chat_id=1, chance=50)
    chance_again = await db.get_or_create_chat(conn, chat_id=1, default_chance=10)
    assert chance_again == 50


async def test_chat_settings_preserve_legacy_chance_and_memory(conn):
    config = make_config(MARKOV_ORDER=5, DIRECT_REPLY_CHANCE=80)
    await db.get_or_create_chat(conn, 1, 25)
    await markov.learn(conn, 1, "сәлем кино", 5)
    before = await db.get_stats(conn, 1)
    settings = await db.get_chat_settings(conn, 1, config)
    assert settings.common_reply_chance == 25
    assert settings.direct_reply_chance == 80
    assert settings.markov_order == 5
    assert await db.get_stats(conn, 1) == before


async def test_settings_persist_are_chat_scoped_and_survive_forget(conn):
    config = make_config()
    await db.set_chat_setting(conn, 1, config, "markov_order", 4)
    await db.set_chat_setting(conn, 1, config, "direct_reply_chance", 75)
    await db.set_chat_setting(conn, 1, config, "meme_chance", 30)
    await db.set_chat_setting(conn, 1, config, "demotivator_chance", 20)
    await db.set_chat_setting(conn, 1, config, "common_reply_chance", 99)
    before = await db.get_chat_settings(conn, 1, config)
    await db.forget_chat(conn, 1)
    assert await db.get_chat_settings(conn, 1, make_config(MARKOV_ORDER=2)) == before
    other = await db.get_chat_settings(conn, 2, config)
    assert other.markov_order == 1
    assert other.direct_reply_chance == 10
    assert before.meme_chance == 30
    assert before.demotivator_chance == 20
    assert before.common_reply_chance == 99


async def test_rejected_media_total_keeps_previous_value(conn):
    config = make_config()
    await db.set_chat_setting(conn, 1, config, "meme_chance", 95)
    with pytest.raises(ValueError):
        await db.set_chat_setting(conn, 1, config, "demotivator_chance", 6)
    assert (await db.get_chat_settings(conn, 1, config)).demotivator_chance == 5


async def test_projected_transitions_sum_weights_without_matching_partial_tokens(conn):
    for _ in range(3):
        await markov.learn(conn, 1, "я люблю кино", 3)
    for _ in range(2):
        await markov.learn(conn, 1, "я люблю театр", 1)
    await markov.learn(conn, 2, "я люблю театр", 3)
    await markov.learn(conn, 1, "я разлюблю цирк", 3)
    assert await db.get_generation_transitions(conn, 1, "люблю") == [("кино", 3), ("театр", 2)]


async def test_upsert_transition_increments_count_on_conflict(conn):
    await db.upsert_transition(conn, chat_id=1, prev="__START__", next_="привет")
    await db.upsert_transition(conn, chat_id=1, prev="__START__", next_="привет")
    await conn.commit()

    rows = await db.get_transitions(conn, chat_id=1, prev="__START__")
    assert rows == [("привет", 2)]


async def test_get_transitions_scoped_to_chat_and_prev(conn):
    await db.upsert_transition(conn, chat_id=1, prev="a", next_="b")
    await db.upsert_transition(conn, chat_id=2, prev="a", next_="c")
    await db.upsert_transition(conn, chat_id=1, prev="x", next_="y")
    await conn.commit()

    rows = await db.get_transitions(conn, chat_id=1, prev="a")
    assert rows == [("b", 1)]


async def test_stats_track_messages_and_derive_transitions_and_photos(conn):
    await db.upsert_transition(conn, chat_id=1, prev="__START__", next_="hi")
    await db.upsert_transition(conn, chat_id=1, prev="hi", next_="__END__")
    await db.increment_messages_learned(conn, chat_id=1)
    await conn.commit()
    await db.add_photo(conn, chat_id=1, file_id="file123")

    stats = await db.get_stats(conn, chat_id=1)
    assert stats == {"messages_learned": 1, "unique_transitions": 2, "photos": 1}


async def test_get_stats_defaults_to_zero_for_unknown_chat(conn):
    stats = await db.get_stats(conn, chat_id=999)
    assert stats == {"messages_learned": 0, "unique_transitions": 0, "photos": 0}


async def test_add_photo_is_idempotent_and_random_photo_returns_saved_id(conn):
    await db.add_photo(conn, chat_id=1, file_id="file123")
    await db.add_photo(conn, chat_id=1, file_id="file123")

    stats = await db.get_stats(conn, chat_id=1)
    assert stats["photos"] == 1
    assert await db.random_photo(conn, chat_id=1) == "file123"


async def test_random_photo_returns_none_when_no_photos(conn):
    assert await db.random_photo(conn, chat_id=1) is None


async def test_forget_chat_removes_only_target_chats_rows(conn):
    await db.get_or_create_chat(conn, chat_id=1, default_chance=10)
    await db.get_or_create_chat(conn, chat_id=2, default_chance=10)
    await db.upsert_transition(conn, chat_id=1, prev="a", next_="b")
    await db.upsert_transition(conn, chat_id=2, prev="a", next_="b")
    await db.increment_messages_learned(conn, chat_id=1)
    await db.increment_messages_learned(conn, chat_id=2)
    await conn.commit()
    await db.add_photo(conn, chat_id=1, file_id="p1")
    await db.add_photo(conn, chat_id=2, file_id="p2")

    await db.forget_chat(conn, chat_id=1)

    stats1 = await db.get_stats(conn, chat_id=1)
    stats2 = await db.get_stats(conn, chat_id=2)
    assert stats1 == {"messages_learned": 0, "unique_transitions": 0, "photos": 0}
    assert stats2 == {"messages_learned": 1, "unique_transitions": 1, "photos": 1}

    # the chats table row itself is untouched by /forget (only chance persists)
    chance = await db.get_or_create_chat(conn, chat_id=1, default_chance=10)
    assert chance == 10
