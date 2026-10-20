from unittest.mock import AsyncMock

from sagynysh.middlewares import AllowedChatsMiddleware
from tests.fakes import make_chat


async def _run(middleware, chat):
    handler = AsyncMock(return_value="handled")
    bot = AsyncMock()
    data = {"event_chat": chat, "bot": bot}
    result = await middleware(handler, event=object(), data=data)
    return handler, bot, result


async def test_allows_when_allowlist_empty():
    middleware = AllowedChatsMiddleware(frozenset())
    handler, bot, result = await _run(middleware, make_chat(chat_id=1, chat_type="group"))

    handler.assert_awaited_once()
    bot.leave_chat.assert_not_awaited()
    assert result == "handled"


async def test_allows_chat_in_allowlist():
    middleware = AllowedChatsMiddleware(frozenset({1, 2}))
    handler, bot, result = await _run(middleware, make_chat(chat_id=1, chat_type="group"))

    handler.assert_awaited_once()
    bot.leave_chat.assert_not_awaited()


async def test_blocks_and_leaves_chat_not_in_allowlist():
    middleware = AllowedChatsMiddleware(frozenset({2}))
    handler, bot, result = await _run(middleware, make_chat(chat_id=1, chat_type="supergroup"))

    handler.assert_not_awaited()
    bot.leave_chat.assert_awaited_once_with(1)
    assert result is None


async def test_ignores_private_chats_regardless_of_allowlist():
    middleware = AllowedChatsMiddleware(frozenset({2}))
    handler, bot, result = await _run(middleware, make_chat(chat_id=1, chat_type="private"))

    handler.assert_awaited_once()
    bot.leave_chat.assert_not_awaited()
