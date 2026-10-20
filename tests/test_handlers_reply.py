import random
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sagynysh import db, markov
from sagynysh.handlers import reply
from tests.fakes import FakeRng, make_config, make_message, make_user


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr(reply.asyncio, "sleep", fast_sleep)


async def _seed_chat(conn, chat_id=1, times=20):
    for _ in range(times):
        await markov.learn(conn, chat_id, "кот сидит дома тихо", order=1)


async def test_always_replies_when_mentioned_by_name(conn):
    await _seed_chat(conn)
    config = make_config(DEFAULT_CHANCE=0)
    message = make_message(text="эй Сглыпа как дела")

    await reply.maybe_reply(
        message, config, conn, bot_username="sagynysh", bot_id=999, rng=random.Random(0)
    )

    message.reply.assert_awaited_once()
    message.answer.assert_not_awaited()


async def test_always_replies_when_mentioned_by_username(conn):
    await _seed_chat(conn)
    config = make_config(DEFAULT_CHANCE=0)
    message = make_message(text="@sagynysh расскажи анекдот")

    await reply.maybe_reply(
        message, config, conn, bot_username="sagynysh", bot_id=999, rng=random.Random(0)
    )

    message.reply.assert_awaited_once()


@pytest.mark.parametrize(
    "chance,roll,should_reply", [(0, 1, False), (30, 30, True), (30, 31, False), (100, 100, True)]
)
async def test_reply_to_bot_uses_independent_direct_chance(conn, chance, roll, should_reply):
    await _seed_chat(conn)
    config = make_config(DEFAULT_CHANCE=100)
    await db.get_or_create_chat(conn, 1, config.default_chance)
    await db.set_chance(conn, 1, 100 - chance)
    await db.set_chat_setting(conn, 1, config, "direct_reply_chance", chance)
    bot_message = SimpleNamespace(from_user=make_user(user_id=999))
    message = make_message(text="ну ладно", reply_to_message=bot_message)
    # Direct replies remain threaded and do not use the random-message cooldown.
    cooldowns = {1: time.monotonic()}
    previous_cooldown = cooldowns[1]

    await reply.maybe_reply(
        message,
        config,
        conn,
        bot_username="sagynysh",
        bot_id=999,
        rng=FakeRng(randint_value=roll),
        cooldowns=cooldowns,
    )

    if should_reply:
        message.reply.assert_awaited_once()
    else:
        message.reply.assert_not_awaited()
        message.bot.send_chat_action.assert_not_awaited()
    message.answer.assert_not_awaited()
    assert cooldowns[1] == previous_cooldown


async def test_silent_when_insufficient_data_even_if_mentioned(conn):
    config = make_config()
    message = make_message(text="эй Сглыпа как дела")

    await reply.maybe_reply(
        message, config, conn, bot_username="sagynysh", bot_id=999, rng=random.Random(0)
    )

    message.reply.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_ignores_commands(conn):
    await _seed_chat(conn)
    config = make_config(DEFAULT_CHANCE=100)
    message = make_message(text="/say")

    await reply.maybe_reply(
        message, config, conn, bot_username="sagynysh", bot_id=999, rng=random.Random(0)
    )

    message.reply.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_random_reply_respects_zero_chance(conn):
    await _seed_chat(conn)
    config = make_config(DEFAULT_CHANCE=0)
    message = make_message(text="просто болтаю в чате")

    await reply.maybe_reply(
        message, config, conn, bot_username="sagynysh", bot_id=999, rng=random.Random(0)
    )

    message.answer.assert_not_awaited()


async def test_random_reply_sends_plain_answer_not_reply(conn):
    await _seed_chat(conn)
    config = make_config(DEFAULT_CHANCE=100)
    message = make_message(text="просто болтаю в чате")

    await reply.maybe_reply(
        message, config, conn, bot_username="sagynysh", bot_id=999, rng=random.Random(0)
    )

    message.answer.assert_awaited_once()
    message.reply.assert_not_awaited()


async def test_random_reply_cooldown_blocks_second_reply(conn):
    await _seed_chat(conn)
    config = make_config(DEFAULT_CHANCE=100)
    cooldowns = {1: time.monotonic()}
    message = make_message(text="просто болтаю в чате")

    await reply.maybe_reply(
        message,
        config,
        conn,
        bot_username="sagynysh",
        bot_id=999,
        rng=random.Random(0),
        cooldowns=cooldowns,
    )

    message.answer.assert_not_awaited()


async def test_random_reply_allowed_after_cooldown_expires(conn):
    await _seed_chat(conn)
    config = make_config(DEFAULT_CHANCE=100)
    cooldowns = {1: time.monotonic() - 20}
    message = make_message(text="просто болтаю в чате")

    await reply.maybe_reply(
        message,
        config,
        conn,
        bot_username="sagynysh",
        bot_id=999,
        rng=random.Random(0),
        cooldowns=cooldowns,
    )

    message.answer.assert_awaited_once()
    assert cooldowns[1] > time.monotonic() - 1


async def test_random_reply_sends_demotivator_on_lucky_roll_with_photo(conn, monkeypatch):
    await _seed_chat(conn)
    await db.add_photo(conn, 1, "p1")
    config = make_config(DEFAULT_CHANCE=100)
    message = make_message(text="просто болтаю в чате")
    fake_send = AsyncMock()
    monkeypatch.setattr(reply.commands, "send_demotivator", fake_send)

    await reply.maybe_reply(
        message,
        config,
        conn,
        bot_username="sagynysh",
        bot_id=999,
        rng=FakeRng(randint_value=1, random_value=0.0),
    )

    fake_send.assert_awaited_once_with(message, config, conn, "p1", as_reply=False)
    message.answer.assert_not_awaited()


async def test_random_reply_skips_demotivator_when_roll_misses(conn, monkeypatch):
    await _seed_chat(conn)
    await db.add_photo(conn, 1, "p1")
    config = make_config(DEFAULT_CHANCE=100)
    message = make_message(text="просто болтаю в чате")
    fake_send = AsyncMock()
    monkeypatch.setattr(reply.commands, "send_demotivator", fake_send)

    await reply.maybe_reply(
        message,
        config,
        conn,
        bot_username="sagynysh",
        bot_id=999,
        rng=FakeRng(randint_value=1, random_value=0.5),
    )

    fake_send.assert_not_awaited()
    message.answer.assert_awaited_once()


async def test_random_reply_skips_demotivator_when_no_photos_saved(conn, monkeypatch):
    await _seed_chat(conn)
    config = make_config(DEFAULT_CHANCE=100)
    message = make_message(text="просто болтаю в чате")
    fake_send = AsyncMock()
    monkeypatch.setattr(reply.commands, "send_demotivator", fake_send)

    await reply.maybe_reply(
        message,
        config,
        conn,
        bot_username="sagynysh",
        bot_id=999,
        rng=FakeRng(randint_value=1, random_value=0.0),
    )

    fake_send.assert_not_awaited()
    message.answer.assert_awaited_once()


async def test_random_reply_demotivator_respects_cooldown(conn, monkeypatch):
    await _seed_chat(conn)
    await db.add_photo(conn, 1, "p1")
    config = make_config(DEFAULT_CHANCE=100)
    cooldowns = {1: time.monotonic()}
    message = make_message(text="просто болтаю в чате")
    fake_send = AsyncMock()
    monkeypatch.setattr(reply.commands, "send_demotivator", fake_send)

    await reply.maybe_reply(
        message,
        config,
        conn,
        bot_username="sagynysh",
        bot_id=999,
        rng=FakeRng(randint_value=1, random_value=0.0),
        cooldowns=cooldowns,
    )

    fake_send.assert_not_awaited()


@pytest.mark.parametrize(
    "roll,kind",
    [
        (0.0, "demotivator"),
        (0.1999, "demotivator"),
        (0.20, "meme"),
        (0.4999, "meme"),
        (0.50, "text"),
        (0.9999, "text"),
    ],
)
async def test_media_chances_have_separate_non_overlapping_shares(conn, monkeypatch, roll, kind):
    await _seed_chat(conn)
    await db.add_photo(conn, 1, "p1")
    config = make_config(DEFAULT_CHANCE=100, MEME_CHANCE=30, DEMOTIVATOR_CHANCE=20)
    meme = AsyncMock()
    demotivator = AsyncMock()
    monkeypatch.setattr(reply.commands, "send_meme", meme)
    monkeypatch.setattr(reply.commands, "send_demotivator", demotivator)
    message = make_message(text="обычное сообщение")
    cooldowns = {}
    await reply.maybe_reply(
        message, config, conn, rng=FakeRng(randint_value=1, random_value=roll), cooldowns=cooldowns
    )
    assert meme.await_count == (kind == "meme")
    assert demotivator.await_count == (kind == "demotivator")
    assert message.answer.await_count == (kind == "text")
    message.reply.assert_not_awaited()
    assert 1 in cooldowns


async def test_media_settings_commands_override_env_for_random_replies(conn, monkeypatch):
    await _seed_chat(conn)
    await db.add_photo(conn, 1, "p1")
    config = make_config(DEFAULT_CHANCE=0, MEME_CHANCE=0, DEMOTIVATOR_CHANCE=0)
    await db.set_chat_setting(conn, 1, config, "common_reply_chance", 100)
    await db.set_chat_setting(conn, 1, config, "meme_chance", 100)
    meme = AsyncMock()
    monkeypatch.setattr(reply.commands, "send_meme", meme)
    message = make_message(text="обычное сообщение")
    await reply.maybe_reply(
        message, config, conn, rng=FakeRng(randint_value=100, random_value=0.99)
    )
    meme.assert_awaited_once_with(message, config, conn, "p1", as_reply=False)


@pytest.mark.parametrize("mentioned", [False, True])
async def test_triggered_replies_stay_text_even_when_all_random_replies_are_images(
    conn, monkeypatch, mentioned
):
    await _seed_chat(conn)
    await db.add_photo(conn, 1, "p1")
    config = make_config(
        DEFAULT_CHANCE=0, DIRECT_REPLY_CHANCE=100, MEME_CHANCE=100, DEMOTIVATOR_CHANCE=0
    )
    meme = AsyncMock()
    monkeypatch.setattr(reply.commands, "send_meme", meme)
    message = make_message(
        text="Сглыпа привет" if mentioned else "привет",
        reply_to_message=make_message(from_user=make_user(user_id=999)),
    )
    await reply.maybe_reply(message, config, conn, bot_id=999, rng=FakeRng(randint_value=1))
    message.reply.assert_awaited_once()
    meme.assert_not_awaited()


async def test_random_images_require_enough_learned_data(conn, monkeypatch):
    await db.add_photo(conn, 1, "p1")
    config = make_config(DEFAULT_CHANCE=100, MEME_CHANCE=100, DEMOTIVATOR_CHANCE=0)
    meme = AsyncMock()
    monkeypatch.setattr(reply.commands, "send_meme", meme)
    message = make_message(text="привет")
    await reply.maybe_reply(message, config, conn, rng=FakeRng(randint_value=1))
    meme.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_random_reply_uses_persisted_markov_order(conn, monkeypatch):
    config = make_config(DEFAULT_CHANCE=100, MEME_CHANCE=0, DEMOTIVATOR_CHANCE=0)
    await db.set_chat_setting(conn, 1, config, "markov_order", 4)
    generate = AsyncMock(return_value="готовый ответ")
    monkeypatch.setattr(markov, "generate", generate)
    await reply.maybe_reply(make_message(text="привет"), config, conn, rng=FakeRng(randint_value=1))
    assert generate.await_args.args[2] == 4
