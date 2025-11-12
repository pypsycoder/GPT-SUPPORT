"""Telegram bot entrypoint for aiogram 3.x MVP."""

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from sqlalchemy import text

from config import BOT_TOKEN
from bots.shared.utils import logger
from app.bot.routers.menu import menu_router
from bots.TG_bot.routers.user_router import register_user_routes
from app.models import Base
from core.db.engine import engine


async def on_startup():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS scales"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS users"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS vitals"))
        await conn.run_sync(Base.metadata.create_all)

    logger.info("✅ База данных инициализирована.")


async def main():
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.include_router(menu_router)
    register_user_routes(dp)

    await on_startup()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
