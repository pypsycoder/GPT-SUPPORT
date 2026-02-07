from __future__ import annotations

# stdlib
import logging
from pathlib import Path

# сторонние библиотеки
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# наше
from app.models import Base  # общий Base, если понадобится metadata
from app.users.api import router as users_api_router
from app.pages.router import router as pages_router
from app.education.router import router as education_router
from app.vitals.router import router as vitals_router
from app.scales.routers import router as scales_router
from app.profile.router import router as profile_router
from core.db.engine import engine

from fastapi.routing import APIRoute

# --- настройка логгера ---

logger = logging.getLogger("gpt-support-api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# === БАЗОВЫЕ ПУТИ ===
# BASE_DIR -> D:\PROJECT\GPT-SUPPORT (корень проекта)
BASE_DIR = Path(__file__).resolve().parent.parent

# FRONTEND_DIR -> D:\PROJECT\GPT-SUPPORT\frontend
FRONTEND_DIR = BASE_DIR / "frontend"


# === Инициализация FastAPI-приложения ===
app = FastAPI(title="GPT Support API")


# === Статика (общий фронтенд) ===
# Всё, что лежит в папке frontend/, доступно по /frontend/...
app.mount(
    "/frontend",
    StaticFiles(directory=str(FRONTEND_DIR)),
    name="frontend",
)


# === Корневой маршрут ===


@app.get("/", include_in_schema=False)
async def serve_root():
    """Главная страница приложения (index)."""
    return FileResponse(FRONTEND_DIR / "index.template.html")


# === Регистрация роутеров API/страниц ===
app.include_router(vitals_router)
app.include_router(users_api_router, prefix="/api/v1")
app.include_router(pages_router)
# app.include_router(education_router, prefix="/api/v1")
app.include_router(education_router, prefix="/api/v1/education")
app.include_router(scales_router, prefix="/api/v1/scales", tags=["scales"])
app.include_router(profile_router, prefix="/api/v1/profile", tags=["profile"])

for route in app.routes:
    if isinstance(route, APIRoute):
        logging.info(
            "ROUTE %s %s",
            route.methods,
            route.path,
        )


# === Cобытие старта приложения ===
@app.on_event("startup")
async def startup() -> None:
    """
    Хук запуска приложения.

    Здесь:
    - проверяем подключение к БД;
    - создаём схемы (идемпотентно).
    Таблицы создаём отдельно через scripts/init_db_from_models.py,
    чтобы не мешать Alembic.
    """
    db: AsyncEngine = engine

    async with db.begin() as conn:
        # создаём схемы, если вдруг их ещё нет
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "vitals"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "users"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "education"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "scales"'))

        # лёгкий health-check
        result = await conn.execute(text("SELECT 1"))
        _ = result.scalar_one_or_none()

    logger.info("✅ GPT Support API запущен, соединение с БД установлено.")

    # выведем все маршруты в лог, чтобы видеть, что /p/... появились
    for route in app.router.routes:
        logger.info(
            "ROUTE %s %s",
            getattr(route, "methods", None),
            getattr(route, "path", None),
        )


# === Эндпоинт здоровья сервиса ===
@app.get("/health")
async def healthcheck() -> dict[str, str]:
    """
    Простой healthcheck-эндпоинт для проверки, что сервис жив.
    """
    return {"status": "ok"}


# === Функция локального запуска через python -m app.main ===
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
