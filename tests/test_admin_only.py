from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetChatAdministrators
from aiogram.types import Message

from sagynysh import db, markov, texts
from sagynysh.handlers import commands, reply
from tests.fakes import make_command, make_config, make_message, make_user

PUBLIC_COMMANDS = ["start", "help", "stats", "say", "meme", "demotivator"]
ADMIN_COMMANDS = [
    "admin_only",
    "chance",
    "common_chance",
    "common_reply_chance",
    "direct_chance",
    "direct_reply_chance",
    "markov_order",
    "meme_chance",
    "demotivator_chance",
    "forget",
]


@pytest.fixture
def command_bot(monkeypatch):
    """Real command filters and routers, with every Telegram operation mocked."""
    bot = Bot("123:fake")
    monkeypatch.setattr(
        bot.session, "make_request", AsyncMock(side_effect=AssertionError("network"))
    )
    monkeypatch.setattr(bot, "get_chat_administrators", AsyncMock(return_value=[]))
    monkeypatch.setattr(bot, "me", AsyncMock(return_value=SimpleNamespace(username="sagynysh")))
    monkeypatch.setattr(Message, "reply", AsyncMock())
    return bot


async def _dispatch(
    bot, conn, text, *, config=None, chat_id=1, chat_type="group", sender_chat=None
):
    message = Message.model_validate(
        {
            "message_id": 1,
            "date": 1,
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"id": 100, "is_bot": False, "first_name": "Test"},
            "text": text,
            "sender_chat": sender_chat,
        },
        context={"bot": bot},
    )
    data = {"bot": bot, "conn": conn, "config": config or make_config()}
    result = await commands.help_router.propagate_event("message", message, **data)
    if result is UNHANDLED:
        result = await commands.router.propagate_event("message", message, **data)
    return message, result


@pytest.mark.parametrize("name", PUBLIC_COMMANDS)
@pytest.mark.parametrize("enabled", [False, True])
async def test_public_commands_follow_toggle_through_real_routers(conn, command_bot, name, enabled):
    await db.set_admin_only(conn, 1, enabled)
    message, result = await _dispatch(command_bot, conn, f"/{name}@sagynysh")
    assert result is not UNHANDLED
    if enabled:
        message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)
    else:
        assert message.reply.await_args.args[0] != texts.CHANCE_NOT_ADMIN
        command_bot.get_chat_administrators.assert_not_awaited()


@pytest.mark.parametrize("name", ADMIN_COMMANDS)
@pytest.mark.parametrize("enabled", [False, True])
async def test_admin_commands_and_aliases_stay_restricted(conn, command_bot, name, enabled):
    await db.set_admin_only(conn, 1, enabled)
    message, result = await _dispatch(command_bot, conn, f"/{name}@sagynysh")
    assert result is not UNHANDLED
    message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)


@pytest.mark.parametrize("name", PUBLIC_COMMANDS + ADMIN_COMMANDS)
async def test_group_admin_can_use_every_command_when_on(conn, command_bot, name):
    await db.set_admin_only(conn, 1, True)
    command_bot.get_chat_administrators.return_value = [SimpleNamespace(user=make_user(100))]
    message, result = await _dispatch(command_bot, conn, f"/{name}", chat_type="supergroup")
    assert result is not UNHANDLED
    assert message.reply.await_args.args[0] != texts.CHANCE_NOT_ADMIN


async def test_configured_bot_admin_can_disable_without_group_admin_lookup(conn, command_bot):
    await db.set_admin_only(conn, 1, True)
    message, _ = await _dispatch(
        command_bot, conn, "/admin_only off", config=make_config(ADMIN_USER_IDS="100")
    )
    assert not await db.get_admin_only(conn, 1)
    message.reply.assert_awaited_once_with(texts.ADMIN_ONLY_STATUS.format(state="off"))
    command_bot.get_chat_administrators.assert_not_awaited()


async def test_group_admin_toggle_takes_effect_immediately_through_routing(conn, command_bot):
    for mode in ["on", "off"]:
        command_bot.get_chat_administrators.return_value = [SimpleNamespace(user=make_user(100))]
        message, _ = await _dispatch(command_bot, conn, f"/admin_only {mode}")
        message.reply.assert_awaited_once_with(texts.ADMIN_ONLY_STATUS.format(state=mode))
        message.reply.reset_mock()
        command_bot.get_chat_administrators.return_value = []
        message, _ = await _dispatch(command_bot, conn, "/say")
        expected = texts.CHANCE_NOT_ADMIN if mode == "on" else texts.NO_DATA
        message.reply.assert_awaited_once_with(expected)
        message.reply.reset_mock()


@pytest.mark.parametrize("args,expected", [("on", True), ("off", False), ("  ON  ", True)])
async def test_admin_only_sets_and_reports_status(conn, args, expected):
    await db.set_admin_only(conn, 1, not expected)
    message = make_message()
    await commands.cmd_admin_only(message, make_command("admin_only", args), make_config(), conn)
    assert await db.get_admin_only(conn, 1) is expected
    message.reply.assert_awaited_once_with(
        texts.ADMIN_ONLY_STATUS.format(state="on" if expected else "off")
    )


@pytest.mark.parametrize("enabled", [False, True])
async def test_admin_only_no_argument_shows_mode_without_changing_it(conn, enabled):
    await db.set_admin_only(conn, 1, enabled)
    message = make_message()
    await commands.cmd_admin_only(message, make_command("admin_only"), make_config(), conn)
    message.reply.assert_awaited_once_with(
        texts.ADMIN_ONLY_STATUS.format(state="on" if enabled else "off")
    )
    assert await db.get_admin_only(conn, 1) is enabled


@pytest.mark.parametrize("args", ["", " ", "yes", "true", "1", "on off", "off extra"])
async def test_admin_only_rejects_malformed_arguments_without_changing_mode(conn, args):
    await db.set_admin_only(conn, 1, True)
    message = make_message()
    await commands.cmd_admin_only(message, make_command("admin_only", args), make_config(), conn)
    message.reply.assert_awaited_once_with(texts.ADMIN_ONLY_USAGE)
    assert await db.get_admin_only(conn, 1)


@pytest.mark.parametrize("args", [None, "on", "off"])
async def test_non_admin_cannot_show_or_change_toggle(conn, args):
    message = make_message(is_admin=False)
    await commands.cmd_admin_only(message, make_command("admin_only", args), make_config(), conn)
    message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)
    assert not await db.get_admin_only(conn, 1)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("name", ["admin_only", "say"])
async def test_lookup_failure_denies_only_commands_requiring_admin(
    conn, command_bot, enabled, name
):
    await db.set_admin_only(conn, 1, enabled)
    command_bot.get_chat_administrators.side_effect = TelegramNetworkError(
        method=GetChatAdministrators(chat_id=1), message="unavailable"
    )
    message, _ = await _dispatch(command_bot, conn, f"/{name}")
    assert (message.reply.await_args.args[0] == texts.CHANCE_NOT_ADMIN) == (
        enabled or name == "admin_only"
    )


@pytest.mark.parametrize("name", ["start", "help", "admin_only on", "say", "chance"])
async def test_private_help_stays_public_and_group_commands_stay_unhandled(conn, command_bot, name):
    await db.set_admin_only(conn, 1, True)
    message, result = await _dispatch(command_bot, conn, f"/{name}", chat_type="private")
    if name in {"start", "help"}:
        message.reply.assert_awaited_once_with(texts.HELP)
    else:
        assert result is UNHANDLED
        message.reply.assert_not_awaited()
    command_bot.get_chat_administrators.assert_not_awaited()


async def test_toggle_is_isolated_between_chats(conn, command_bot):
    await db.set_admin_only(conn, 1, True)
    message, _ = await _dispatch(command_bot, conn, "/say", chat_id=2)
    message.reply.assert_awaited_once_with(texts.NO_DATA)
    command_bot.get_chat_administrators.assert_not_awaited()
    assert not await db.get_admin_only(conn, 2)


async def test_command_gate_rechecks_admin_rights_in_each_chat_and_after_demotion(
    conn, command_bot
):
    await db.set_admin_only(conn, 1, True)
    await db.set_admin_only(conn, 2, True)
    command_bot.get_chat_administrators.side_effect = lambda chat_id: (
        [SimpleNamespace(user=make_user(100))] if chat_id == 1 else []
    )
    message, _ = await _dispatch(command_bot, conn, "/say")
    message.reply.assert_awaited_once_with(texts.NO_DATA)
    message.reply.reset_mock()
    message, _ = await _dispatch(command_bot, conn, "/say", chat_id=2)
    message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)
    message.reply.reset_mock()
    command_bot.get_chat_administrators.side_effect = None
    command_bot.get_chat_administrators.return_value = []
    message, _ = await _dispatch(command_bot, conn, "/say")
    message.reply.assert_awaited_once_with(texts.CHANCE_NOT_ADMIN)


@pytest.mark.parametrize("sender_chat_id,allowed", [(1, True), (-100999, False)])
async def test_anonymous_group_admin_is_recognized_by_command_gate(
    conn, command_bot, sender_chat_id, allowed
):
    await db.set_admin_only(conn, 1, True)
    message, _ = await _dispatch(
        command_bot, conn, "/say", sender_chat={"id": sender_chat_id, "type": "supergroup"}
    )
    assert (message.reply.await_args.args[0] != texts.CHANCE_NOT_ADMIN) is allowed
    command_bot.get_chat_administrators.assert_not_awaited()


async def test_toggle_defaults_off_and_preserves_legacy_settings_and_memory(conn):
    config = make_config()
    await markov.learn(conn, 1, "кот сидит дома", 1)
    settings = await db.get_chat_settings(conn, 1, config)
    stats = await db.get_stats(conn, 1)
    assert not await db.get_admin_only(conn, 1)
    await db.set_admin_only(conn, 1, True)
    assert await db.get_chat_settings(conn, 1, config) == settings
    assert await db.get_stats(conn, 1) == stats
    await db.forget_chat(conn, 1)
    assert await db.get_admin_only(conn, 1)


async def test_toggle_survives_database_restore_and_schema_initialization():
    """Reload persisted SQLite contents into a fresh in-memory connection."""
    original = await db.connect(":memory:")
    try:
        await db.set_admin_only(original, 1, True)
        await db.set_admin_only(original, 2, False)
        dump = "\n".join([line async for line in original.iterdump()])
    finally:
        await original.close()
    import aiosqlite

    restored = await aiosqlite.connect(":memory:")
    restored.row_factory = aiosqlite.Row
    try:
        await restored.executescript(dump)
        await restored.executescript(db.SCHEMA)
        assert await db.get_admin_only(restored, 1)
        assert not await db.get_admin_only(restored, 2)
        assert not await db.get_admin_only(restored, 3)
    finally:
        await restored.close()


@pytest.mark.parametrize("kind", ["ordinary", "direct", "mention", "meme", "demotivator"])
async def test_admin_only_keeps_automatic_response_behavior(conn, monkeypatch, kind):
    await db.set_admin_only(conn, 1, True)
    for _ in range(20):
        await markov.learn(conn, 1, "кот сидит дома", 1)
    await db.add_photo(conn, 1, "p1")
    media = kind in {"meme", "demotivator"}
    config = make_config(
        COMMON_REPLY_CHANCE=100 if kind != "mention" else 0,
        DIRECT_REPLY_CHANCE=100 if kind == "direct" else 0,
        MEME_CHANCE=100 if kind == "meme" else 0,
        DEMOTIVATOR_CHANCE=100 if kind == "demotivator" else 0,
    )
    message = make_message(
        text="Сглыпа привет" if kind == "mention" else "привет",
        is_admin=False,
        reply_to_message=make_message(from_user=make_user(999)) if kind == "direct" else None,
    )
    monkeypatch.setattr(reply.asyncio, "sleep", AsyncMock())
    meme, demotivator = AsyncMock(), AsyncMock()
    monkeypatch.setattr(commands, "send_meme", meme)
    monkeypatch.setattr(commands, "send_demotivator", demotivator)
    await reply.maybe_reply(message, config, conn, bot_id=999, cooldowns={})
    assert meme.await_count == (kind == "meme")
    assert demotivator.await_count == (kind == "demotivator")
    assert message.reply.await_count == (kind in {"direct", "mention"})
    assert message.answer.await_count == (kind == "ordinary")
    assert message.bot.send_chat_action.await_count == 1
    message.bot.get_chat_administrators.assert_not_awaited()
    assert media or message.reply.await_count + message.answer.await_count == 1


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("direct", [False, True])
async def test_zero_reply_probabilities_stay_silent_in_both_modes(conn, enabled, direct):
    await db.set_admin_only(conn, 1, enabled)
    for _ in range(20):
        await markov.learn(conn, 1, "кот сидит дома", 1)
    config = make_config(COMMON_REPLY_CHANCE=0, DIRECT_REPLY_CHANCE=0)
    message = make_message(
        text="привет",
        reply_to_message=make_message(from_user=make_user(999)) if direct else None,
    )
    await reply.maybe_reply(message, config, conn, bot_id=999)
    message.reply.assert_not_awaited()
    message.answer.assert_not_awaited()
    message.bot.send_chat_action.assert_not_awaited()


def test_admin_only_is_in_command_menu_and_help():
    assert "admin_only" in {command.command for command in commands.BOT_COMMANDS}
    assert "/admin_only [on|off]" in texts.HELP
