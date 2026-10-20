from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetChatAdministrators

from sagynysh import db, markov, texts
from sagynysh.handlers import commands
from tests.fakes import (
    make_callback,
    make_command,
    make_config,
    make_downloaded_photo,
    make_message,
    make_photo,
    make_user,
)


async def _seed_chat(conn, chat_id=1, times=20):
    for _ in range(times):
        await markov.learn(conn, chat_id, "кот сидит дома тихо", order=1)


async def test_help_replies_with_help_text_in_private_and_group():
    for chat_type in ("private", "group"):
        message = make_message(text="/help", chat_id=1)
        message.chat.type = chat_type

        await commands.cmd_help(message)

        message.reply.assert_awaited_once_with(texts.HELP)


async def test_say_replies_no_data_below_threshold(conn):
    config = make_config()
    message = make_message(text="/say")

    await commands.cmd_say(message, config, conn)

    message.reply.assert_awaited_once_with(texts.NO_DATA)


async def test_say_replies_with_generated_text_once_learned(conn):
    await _seed_chat(conn)
    config = make_config()
    message = make_message(text="/say")

    await commands.cmd_say(message, config, conn)

    message.reply.assert_awaited_once()
    (sent_text,), _ = message.reply.call_args
    assert sent_text != texts.NO_DATA
    assert sent_text


async def test_chance_shows_current_value_without_args(conn):
    config = make_config(DEFAULT_CHANCE=17)
    message = make_message(text="/chance")

    await commands.cmd_chance(message, make_command("chance", args=None), config, conn)

    message.reply.assert_awaited_once_with(
        texts.SETTING_SHOW.format(
            label=texts.SETTING_NAMES["common_reply_chance"], value=17, unit="%"
        )
    )


async def test_chance_allows_chat_admin_without_configured_bot_admins(conn):
    config = make_config()
    message = make_message(text="/chance 42")

    await commands.cmd_chance(message, make_command("chance", args="42"), config, conn)

    message.reply.assert_awaited_once_with(
        texts.SETTING_SET.format(
            label=texts.SETTING_NAMES["common_reply_chance"], value=42, unit="%"
        )
    )
    assert await db.get_or_create_chat(conn, 1, 10) == 42


async def test_chance_rejects_non_admin_when_admin_ids_configured(conn):
    config = make_config(ADMIN_USER_IDS="999")
    message = make_message(text="/chance 42", from_user=make_user(user_id=1), is_admin=False)

    await commands.cmd_chance(message, make_command("chance", args="42"), config, conn)

    message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)
    assert await db.get_or_create_chat(conn, 1, 10) == 10


async def test_chance_allows_admin_when_admin_ids_configured(conn):
    config = make_config(ADMIN_USER_IDS="999")
    message = make_message(text="/chance 42", from_user=make_user(user_id=999), is_admin=False)

    await commands.cmd_chance(message, make_command("chance", args="42"), config, conn)

    message.reply.assert_awaited_once_with(
        texts.SETTING_SET.format(
            label=texts.SETTING_NAMES["common_reply_chance"], value=42, unit="%"
        )
    )


async def test_chance_rejects_out_of_range_value(conn):
    config = make_config()
    message = make_message(text="/chance 200")

    await commands.cmd_chance(message, make_command("chance", args="200"), config, conn)

    message.reply.assert_awaited_once_with(texts.CHANCE_INVALID)


async def test_chance_rejects_non_numeric_value(conn):
    config = make_config()
    message = make_message(text="/chance abc")

    await commands.cmd_chance(message, make_command("chance", args="abc"), config, conn)

    message.reply.assert_awaited_once_with(texts.CHANCE_INVALID)


async def test_stats_reports_counts(conn):
    await _seed_chat(conn, times=1)
    message = make_message(text="/stats")

    await commands.cmd_stats(message, conn)

    stats = await db.get_stats(conn, 1)
    message.reply.assert_awaited_once_with(texts.STATS.format(chat_id=message.chat.id, **stats))


async def test_demotivator_replies_no_photos_when_none_saved(conn):
    config = make_config()
    message = make_message(text="/demotivator")

    await commands.cmd_demotivator(message, config, conn)

    message.reply.assert_awaited_once_with(texts.NO_PHOTOS)
    message.reply_photo.assert_not_awaited()


async def test_demotivator_uses_random_saved_photo(conn):
    await _seed_chat(conn)
    await db.add_photo(conn, 1, "p1")
    config = make_config()
    message = make_message(text="/demotivator")
    message.bot.download.return_value = make_downloaded_photo()

    await commands.cmd_demotivator(message, config, conn)

    message.bot.download.assert_awaited_once_with("p1")
    message.reply_photo.assert_awaited_once()
    (input_file,), _ = message.reply_photo.call_args
    assert input_file.data[:2] == b"\xff\xd8"


async def test_demotivator_prefers_photo_being_replied_to(conn):
    await _seed_chat(conn)
    await db.add_photo(conn, 1, "random1")
    config = make_config()
    reply_target = make_message(photo=[make_photo("replied1")])
    message = make_message(text="/demotivator", reply_to_message=reply_target)
    message.bot.download.return_value = make_downloaded_photo()

    await commands.cmd_demotivator(message, config, conn)

    message.bot.download.assert_awaited_once_with("replied1")


async def test_meme_replies_no_photos_when_none_saved(conn):
    config = make_config()
    message = make_message(text="/meme")

    await commands.cmd_meme(message, config, conn)

    message.reply.assert_awaited_once_with(texts.NO_PHOTOS)
    message.reply_photo.assert_not_awaited()


async def test_meme_uses_random_saved_photo(conn):
    await _seed_chat(conn)
    await db.add_photo(conn, 1, "p1")
    config = make_config()
    message = make_message(text="/meme")
    message.bot.download.return_value = make_downloaded_photo()

    await commands.cmd_meme(message, config, conn)

    message.bot.download.assert_awaited_once_with("p1")
    message.reply_photo.assert_awaited_once()
    (input_file,), _ = message.reply_photo.call_args
    assert input_file.data[:2] == b"\xff\xd8"


async def test_send_demotivator_as_reply_false_uses_answer_photo(conn):
    await _seed_chat(conn)
    config = make_config()
    message = make_message()
    message.bot.download.return_value = make_downloaded_photo()

    await commands.send_demotivator(message, config, conn, "p1", as_reply=False)

    message.answer_photo.assert_awaited_once()
    message.reply_photo.assert_not_awaited()


async def test_forget_asks_for_confirmation(conn):
    config = make_config()
    message = make_message(text="/forget")

    await commands.cmd_forget(message, config)

    message.reply.assert_awaited_once()
    (sent_text,), kwargs = message.reply.call_args
    assert sent_text == texts.FORGET_CONFIRM
    keyboard = kwargs["reply_markup"]
    buttons = [b.text for row in keyboard.inline_keyboard for b in row]
    assert texts.FORGET_BUTTON_YES in buttons
    assert texts.FORGET_BUTTON_NO in buttons


async def test_forget_rejects_non_admin(conn):
    config = make_config(ADMIN_USER_IDS="999")
    message = make_message(text="/forget", from_user=make_user(user_id=1), is_admin=False)

    await commands.cmd_forget(message, config)

    message.reply.assert_awaited_once_with(texts.FORGET_NOT_ADMIN)


async def test_cb_forget_yes_wipes_chat_and_edits_message(conn):
    await _seed_chat(conn, times=1)
    config = make_config()
    callback = make_callback("forget:yes")

    await commands.cb_forget(callback, config, conn)

    stats = await db.get_stats(conn, 1)
    assert stats == {"messages_learned": 0, "unique_transitions": 0, "photos": 0}
    callback.message.edit_text.assert_awaited_once_with(texts.FORGET_DONE)
    callback.answer.assert_awaited_once()


async def test_cb_forget_no_cancels_without_wiping(conn):
    await _seed_chat(conn, times=1)
    config = make_config()
    callback = make_callback("forget:no")

    await commands.cb_forget(callback, config, conn)

    stats = await db.get_stats(conn, 1)
    assert stats["messages_learned"] == 1
    callback.message.edit_text.assert_awaited_once_with(texts.FORGET_CANCELLED)


async def test_cb_forget_rejects_non_admin(conn):
    await _seed_chat(conn, times=1)
    config = make_config(ADMIN_USER_IDS="999")
    callback = make_callback("forget:yes", from_user=make_user(user_id=1), is_admin=False)

    await commands.cb_forget(callback, config, conn)

    stats = await db.get_stats(conn, 1)
    assert stats["messages_learned"] == 1
    callback.answer.assert_awaited_once_with(texts.FORGET_NOT_ADMIN, show_alert=True)


SETTINGS_COMMANDS = [
    (commands.cmd_chance, "chance", "common_reply_chance", 42),
    (commands.cmd_direct_chance, "direct_chance", "direct_reply_chance", 80),
    (commands.cmd_markov_order, "markov_order", "markov_order", 5),
    (commands.cmd_meme_chance, "meme_chance", "meme_chance", 35),
    (commands.cmd_demotivator_chance, "demotivator_chance", "demotivator_chance", 30),
]


@pytest.mark.parametrize("handler,command,name,value", SETTINGS_COMMANDS)
async def test_each_setting_command_sets_and_shows_only_this_chat(
    conn, handler, command, name, value
):
    config = make_config(ADMIN_USER_IDS="999")
    message = make_message()
    before = await db.get_chat_settings(conn, 2, config)
    await handler(message, make_command(command, str(value)), config, conn)
    assert getattr(await db.get_chat_settings(conn, 1, config), name) == value
    assert await db.get_chat_settings(conn, 2, config) == before
    message.bot.get_chat_administrators.assert_awaited_once_with(1)
    message.reply.reset_mock()
    await handler(message, make_command(command), config, conn)
    unit = "" if name == "markov_order" else "%"
    message.reply.assert_awaited_once_with(
        texts.SETTING_SHOW.format(label=texts.SETTING_NAMES[name], value=value, unit=unit)
    )


@pytest.mark.parametrize("handler,command,name,value", SETTINGS_COMMANDS)
@pytest.mark.parametrize("args", [None, "42"])
async def test_all_settings_commands_reject_non_admins_even_with_empty_admin_list(
    conn, handler, command, name, value, args
):
    config = make_config()
    before = await db.get_chat_settings(conn, 1, config)
    message = make_message(is_admin=False)
    await handler(message, make_command(command, args), config, conn)
    message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)
    assert await db.get_chat_settings(conn, 1, config) == before


@pytest.mark.parametrize("handler,command,name,value", SETTINGS_COMMANDS)
@pytest.mark.parametrize("args", ["abc", "1.5", "-1", "101", "1 2"])
async def test_all_settings_commands_reject_invalid_values(
    conn, handler, command, name, value, args
):
    config = make_config()
    before = await db.get_chat_settings(conn, 1, config)
    message = make_message()
    await handler(message, make_command(command, args), config, conn)
    assert await db.get_chat_settings(conn, 1, config) == before
    low, high = (1, 5) if name == "markov_order" else (0, 100)
    message.reply.assert_awaited_once_with(texts.SETTING_INVALID.format(low=low, high=high))


async def test_media_command_rejects_total_above_100(conn):
    config = make_config(MEME_CHANCE=70, DEMOTIVATOR_CHANCE=30)
    message = make_message()
    await commands.cmd_demotivator_chance(
        message, make_command("demotivator_chance", "31"), config, conn
    )
    message.reply.assert_awaited_once_with(texts.MEDIA_CHANCE_INVALID)
    assert (await db.get_chat_settings(conn, 1, config)).demotivator_chance == 30


async def test_permissions_are_rechecked_after_admin_demotion(conn):
    config = make_config()
    message = make_message()
    await commands.cmd_chance(message, make_command("chance", "25"), config, conn)
    message.bot.get_chat_administrators.return_value = []
    message.reply.reset_mock()
    await commands.cmd_chance(message, make_command("chance", "90"), config, conn)
    message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)
    assert (await db.get_chat_settings(conn, 1, config)).common_reply_chance == 25


async def test_admin_of_one_chat_has_no_rights_in_another(conn):
    config = make_config()
    message = make_message()
    message.bot.get_chat_administrators.side_effect = lambda chat_id: (
        [SimpleNamespace(user=message.from_user)] if chat_id == 1 else []
    )
    await commands.cmd_chance(message, make_command("chance", "25"), config, conn)
    message.chat.id = 2
    message.reply.reset_mock()
    await commands.cmd_chance(message, make_command("chance", "90"), config, conn)
    message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)
    assert (await db.get_chat_settings(conn, 2, config)).common_reply_chance == 10


async def test_admin_lookup_failure_denies_access(conn):
    message = make_message()
    message.bot.get_chat_administrators.side_effect = TelegramNetworkError(
        method=GetChatAdministrators(chat_id=1), message="unavailable"
    )
    await commands.cmd_chance(message, make_command("chance", "50"), make_config(), conn)
    message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)


@pytest.mark.parametrize("sender_chat_id,allowed", [(1, True), (-100999, False)])
async def test_anonymous_admin_allowed_but_channel_sender_rejected(conn, sender_chat_id, allowed):
    message = make_message(
        sender_chat=SimpleNamespace(id=sender_chat_id), from_user=make_user(is_bot=True)
    )
    config = make_config()
    await commands.cmd_chance(message, make_command("chance", "50"), config, conn)
    settings = await db.get_chat_settings(conn, 1, config)
    assert settings.common_reply_chance == (50 if allowed else 10)
    message.bot.get_chat_administrators.assert_not_awaited()


async def test_forget_button_rechecks_admin_rights_at_confirmation(conn):
    await _seed_chat(conn)
    config = make_config()
    message = make_message()
    await commands.cmd_forget(message, config)
    callback = make_callback("forget:yes", is_admin=False)
    await commands.cb_forget(callback, config, conn)
    assert (await db.get_stats(conn, 1))["messages_learned"] == 20
    callback.answer.assert_awaited_once_with(texts.FORGET_NOT_ADMIN, show_alert=True)


async def test_say_and_caption_use_persisted_order(conn, monkeypatch):
    from unittest.mock import AsyncMock

    config = make_config()
    await db.set_chat_setting(conn, 1, config, "markov_order", 5)
    generate = AsyncMock(return_value="слова из чата")
    monkeypatch.setattr(markov, "generate", generate)
    message = make_message()
    await commands.cmd_say(message, config, conn)
    await commands._generate_caption(message, config, conn)
    assert generate.await_count == 2
    for call in generate.await_args_list:
        assert call.args[2] == 5
