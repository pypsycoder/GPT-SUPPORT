# core/db/engine.py
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# --- грузим .env рядом с корнем проекта ---

BASE_DIR = Path(__file__).resolve().parents[2]  # .../GPT-SUPPORT/core/db -> parents[2] = GPT-SUPPORT
env_file = os.getenv("ENV_FILE") or ".env"
env_path = BASE_DIR / env_file
if not env_path.exists():
    env_path = BASE_DIR / ".env"

load_dotenv(env_path)

# --- берём URL из .env ---

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("Нет DATABASE_URL в .env")

# --- создаём async engine и фабрику сессий ---

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
