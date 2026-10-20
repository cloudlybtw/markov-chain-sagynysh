import pytest
from aiogram.dispatcher.event.bases import SkipHandler

from sagynysh import db
from sagynysh.handlers import learn
from tests.fakes import make_config, make_message, make_photo, make_user


async def test_learn_text_learns_eligible_message_and_skips(conn):
    config = make_config()
    message = make_message(text="кот сидит дома тихо")

    with pytest.raises(SkipHandler):
        await learn.learn_text(message, config, conn)

    stats = await db.get_stats(conn, chat_id=1)
    assert stats["messages_learned"] == 1


async def test_learn_text_skips_commands(conn):
    config = make_config()
    message = make_message(text="/start")

    with pytest.raises(SkipHandler):
        await learn.learn_text(message, config, conn)

    stats = await db.get_stats(conn, chat_id=1)
    assert stats["messages_learned"] == 0


async def test_learn_text_skips_bot_sender(conn):
    config = make_config()
    message = make_message(text="привет всем сегодня", from_user=make_user(is_bot=True))

    with pytest.raises(SkipHandler):
        await learn.learn_text(message, config, conn)

    stats = await db.get_stats(conn, chat_id=1)
    assert stats["messages_learned"] == 0


async def test_learn_text_skips_forwarded(conn):
    config = make_config()
    message = make_message(text="привет всем сегодня", forward_origin=object())

    with pytest.raises(SkipHandler):
        await learn.learn_text(message, config, conn)

    stats = await db.get_stats(conn, chat_id=1)
    assert stats["messages_learned"] == 0


async def test_learn_text_strips_bot_self_mention(conn):
    config = make_config()
    message = make_message(text="@sagynysh привет всем такое")

    with pytest.raises(SkipHandler):
        await learn.learn_text(message, config, conn, bot_username="sagynysh")

    rows = await db.get_transitions(conn, chat_id=1, prev="__START__")
    next_words = [word for word, _ in rows]
    assert "@sagynysh" not in next_words
    assert "привет" in next_words


async def test_learn_photo_saves_photo_and_learns_caption(conn):
    config = make_config()
    message = make_message(photo=[make_photo("p1")], caption="кот сидит дома тихо")

    with pytest.raises(SkipHandler):
        await learn.learn_photo(message, config, conn)

    assert await db.random_photo(conn, chat_id=1) == "p1"
    stats = await db.get_stats(conn, chat_id=1)
    assert stats["messages_learned"] == 1


async def test_learn_photo_without_caption_only_saves_photo(conn):
    config = make_config()
    message = make_message(photo=[make_photo("p1")], caption=None)

    with pytest.raises(SkipHandler):
        await learn.learn_photo(message, config, conn)

    assert await db.random_photo(conn, chat_id=1) == "p1"
    stats = await db.get_stats(conn, chat_id=1)
    assert stats["messages_learned"] == 0


@pytest.mark.parametrize("photo", [False, True])
async def test_learning_uses_chat_order_override(conn, photo):
    config = make_config(MARKOV_ORDER=1)
    await db.set_chat_setting(conn, 1, config, "markov_order", 5)
    if photo:
        message = make_message(photo=[make_photo("p1")], caption="сәлем әлем")
        handler = learn.learn_photo
    else:
        message = make_message(text="сәлем әлем")
        handler = learn.learn_text
    with pytest.raises(SkipHandler):
        await handler(message, config, conn)
    assert await db.get_transitions(conn, 1, "\x1f".join(["__START__"] * 5)) == [("сәлем", 1)]
    assert await db.get_transitions(conn, 1, "__START__") == []
