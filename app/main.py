# ============================================
# GPT Support API: Точка входа FastAPI-приложения
# ============================================
# Инициализация FastAPI, регистрация роутеров, CORS,
# статика, подключение к PostgreSQL и создание схем.

from __future__ import annotations

# stdlib
import logging
from pathlib import Path

# сторонние библиотеки
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
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
from app.auth.router import router as auth_router
from app.consent.router import router as consent_router
from app.researchers.router import router as researcher_router
from app.dialysis.router import router as dialysis_router
from app.sleep_tracker.router import router as sleep_tracker_router
from app.routine.router import router as routine_router
from app.medications.router import router as medications_router
from app.practices.router import router as practices_router
from app.scales.routers import kdqol_patient_router, kdqol_researcher_router
from app.routers.chat import router as chat_router
from core.db.engine import engine

from fastapi.routing import APIRoute

# --- Настройка логгера ---

logger = logging.getLogger("gpt-support-api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# ============================================
#   Базовые пути
# ============================================
# BASE_DIR -> D:\PROJECT\GPT-SUPPORT (корень проекта)
BASE_DIR = Path(__file__).resolve().parent.parent

# FRONTEND_DIR -> D:\PROJECT\GPT-SUPPORT\frontend
FRONTEND_DIR = BASE_DIR / "frontend"


# --- Инициализация FastAPI ---
app = FastAPI(title="GPT Support API")


# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Статика ---
# Всё, что лежит в папке frontend/, доступно по /frontend/...
app.mount(
    "/frontend",
    StaticFiles(directory=str(FRONTEND_DIR)),
    name="frontend",
)


# --- Корневой маршрут ---


@app.get("/", include_in_schema=False)
async def serve_root():
    """Корневой маршрут — перенаправляем на страницу входа."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login")


# ============================================
#   Регистрация роутеров
# ============================================
app.include_router(vitals_router, prefix="/api/v1")
app.include_router(users_api_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(consent_router, prefix="/api/v1")
app.include_router(researcher_router, prefix="/api/v1")
app.include_router(dialysis_router, prefix="/api/v1")
app.include_router(sleep_tracker_router, prefix="/api/v1")
app.include_router(routine_router, prefix="/api/v1")
app.include_router(medications_router, prefix="/api")
app.include_router(practices_router, prefix="/api")
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(pages_router)
# app.include_router(education_router, prefix="/api/v1")
app.include_router(education_router, prefix="/api/v1/education")
app.include_router(scales_router, prefix="/api/v1/scales", tags=["scales"])
app.include_router(profile_router, prefix="/api/v1/profile", tags=["profile"])
app.include_router(kdqol_patient_router, prefix="/api/v1")
app.include_router(kdqol_researcher_router, prefix="/api/v1")

for route in app.routes:
    if isinstance(route, APIRoute):
        logging.info(
            "ROUTE %s %s",
            route.methods,
            route.path,
        )


# ============================================
#   Startup и healthcheck
# ============================================
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
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "sleep"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "medications"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "kdqol"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "practices"'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "llm"'))

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


# --- Healthcheck ---
@app.get("/health")
async def healthcheck() -> dict[str, str]:
    """
    Простой healthcheck-эндпоинт для проверки, что сервис жив.
    """
    return {"status": "ok"}


# --- Локальный запуск ---
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
