# main.py — запуск Telegram-бота
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from config import BOT_TOKEN
from bots.TG_bot.routers.user_router import register_user_routes
from bots.shared.utils import logger
from sqlalchemy import text

# импортируем базы моделей
from app.models import Base
from core.db.engine import engine

async def on_startup():
    async with engine.begin() as conn:
        # 💡 принудительно создать схему (даже если уже есть — не страшно)
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS scales"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS users"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS vitals"))

        # 🔧 теперь создаём все таблицы из объединённого Base
        await conn.run_sync(Base.metadata.create_all)

    logger.info("✅ База данных инициализирована.")
async def main():
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    register_user_routes(dp)
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
