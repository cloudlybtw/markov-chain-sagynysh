"""Entry point: python -m sagynysh"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from sagynysh.config import load_config
from sagynysh.db import connect
from sagynysh.handlers import commands, learn, reply
from sagynysh.middlewares import AllowedChatsMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    conn = await connect(config.db_path)
    bot = Bot(token=config.bot_token)

    try:
        me = await bot.get_me()
        bot_username = me.username or ""
        await bot.set_my_commands(commands.BOT_COMMANDS)

        dp = Dispatcher()
        dp["conn"] = conn
        dp["config"] = config
        dp["bot_username"] = bot_username
        dp["bot_id"] = bot.id
        dp["cooldowns"] = {}

        dp.message.outer_middleware(AllowedChatsMiddleware(config.allowed_chat_ids))
        dp.callback_query.outer_middleware(AllowedChatsMiddleware(config.allowed_chat_ids))
        dp.include_router(commands.help_router)
        dp.include_router(commands.router)
        dp.include_router(learn.router)
        dp.include_router(reply.router)

        logger.info("sagynysh: starting polling as @%s", bot_username)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
