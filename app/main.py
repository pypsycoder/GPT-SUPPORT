from __future__ import annotations

# stdlib
import logging

# сторонние библиотеки
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# наше
from app.models import Base  # общий Base, если понадобится metadata
from app.vitals.router import router as vitals_router
from core.db.engine import engine
from app.users.api import router as users_api_router            #FastApi роутер


# --- настройка логгера ---

logger = logging.getLogger("gpt-support-api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


# # инициализация FastAPI-приложения
app = FastAPI(title="GPT Support API")

# # регистрация роутеров
app.include_router(vitals_router)
app.include_router(users_api_router, prefix="/api/v1")         # FastApi


# # событие старта приложения
@app.on_event("startup")
async def startup() -> None:
    """
    Хук запуска приложения.

    Здесь:
    - проверяем подключение к БД;
    - при необходимости можем создавать схемы (идемпотентно).
    Таблицы мы теперь создаём отдельно через scripts/init_db_from_models.py,
    чтобы не мешать Alembic и не плодить разносы между средами.
    """
    db: AsyncEngine = engine

    async with db.begin() as conn:
        # создаём схемы, если вдруг их ещё нет
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "vitals"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "users"'))

        # Можно добавить лёгкий health-check, чтобы поймать проблемы
        result = await conn.execute(text("SELECT 1"))
        _ = result.scalar_one_or_none()

    logger.info("✅ GPT Support API запущен, соединение с БД установлено.")


# # эндпоинт здоровья сервиса
@app.get("/health")
async def healthcheck() -> dict[str, str]:
    """
    Простой healthcheck-эндпоинт для проверки, что сервис жив.
    """
    return {"status": "ok"}


# # функция запуска через python -m / прямой вызов файла
def run() -> None:
    """
    Локальный запуск приложения через uvicorn.
    Используется, если хочется запустить API отдельно от бота.
    """
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    run()
