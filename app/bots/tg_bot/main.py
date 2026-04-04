"""Telegram bot entrypoint for aiogram 3.x."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import text

from app.core.config import load_environment


load_environment()

from app.bots.tg_bot.handlers import vitals
from app.bots.tg_bot.middlewares.db import DBSessionMiddleware
from app.bots.tg_bot.routers import menu_inline, user_router
from bots.shared.utils import logger
from config import BOT_TOKEN
from core.db.engine import async_session_maker, engine


async def on_startup() -> None:
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        _ = result.scalar_one_or_none()

    logger.info("Database connection established.")


async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.update.middleware(DBSessionMiddleware(async_session_maker))
    dp.include_router(vitals.router)
    dp.include_router(menu_inline.menu_router)
    user_router.register_user_routes(dp)

    await on_startup()

    logger.info("Telegram bot started.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
