"""Telegram bot entrypoint for aiogram 3.x."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import text

from config import BOT_TOKEN
from bots.shared.utils import logger
from core.db.engine import engine, async_session_maker
from app.bots.tg_bot.routers import menu_inline, user_router
from app.bots.tg_bot.handlers import vitals
from app.bots.tg_bot.middlewares.db import DBSessionMiddleware


async def on_startup() -> None:
    """
    Стартовый хук бота.

    Здесь:
    - проверяем соединение с БД (лёгкий health-check),
    - создаём схемы, если их вдруг ещё нет (идемпотентно).

    Таблицы мы больше НЕ создаём отсюда:
    их один раз поднимает scripts/init_db_from_models.py,
    а актуальность схемы дальше отслеживает Alembic.
    """
    async with engine.begin() as conn:
        # Идемпотентно создаём схемы (на всякий случай).
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "scales"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "users"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "vitals"'))

        # Лёгкая проверка связи с БД.
        result = await conn.execute(text("SELECT 1"))
        _ = result.scalar_one_or_none()

    logger.info("✅ Соединение с БД установлено, схемы проверены.")


async def main() -> None:
    """
    Главная точка входа Telegram-бота.

    Делает:
    - создаёт Bot с корректным DefaultBotProperties,
    - настраивает Dispatcher,
    - вешает middleware с AsyncSession,
    - подключает все роутеры,
    - вызывает on_startup и запускает polling.
    """
    # Создаём бота c DefaultBotProperties вместо устаревшего parse_mode в конструкторе.
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Диспетчер aiogram 3.x
    dp = Dispatcher()

    # 🔹 Middleware БД: на каждый апдейт создаёт AsyncSession и кладёт в data["session"]
    dp.update.middleware(DBSessionMiddleware(async_session_maker))

    # 🔹 Подключаем vitals-хендлеры (давление, пульс, вес)
    dp.include_router(vitals.router)

    # 🔹 Остальные роутеры бота (меню, профиль и т.д.)
    dp.include_router(menu_inline.menu_router)
    user_router.register_user_routes(dp)

    # Стартовые действия: проверка БД, логирование
    await on_startup()

    logger.info("🤖 Telegram-бот запущен. Ожидаем апдейты...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
