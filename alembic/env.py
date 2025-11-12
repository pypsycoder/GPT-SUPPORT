"""Alembic environment setup (sync engine, schema filtering, .env support)."""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Paths & .env
# ------------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Prefer .env.test if ENV_FILE is not set; fallback to .env
env_file = os.getenv("ENV_FILE") or ".env.test"
env_path = BASE_DIR / env_file
if not env_path.exists():
    env_path = BASE_DIR / ".env"
load_dotenv(env_path)

# ------------------------------------------------------------------------------
# Alembic config & logging
# ------------------------------------------------------------------------------

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ------------------------------------------------------------------------------
# Project metadata (IMPORT YOUR BASE HERE)
# ------------------------------------------------------------------------------

# Если у тебя Base лежит в другом месте — поправь импорт
from app.models import Base  # noqa
import app.users.models      # noqa: F401
import app.scales.models     # noqa: F401
import app.vitals.models     # noqa: F401

target_metadata = Base.metadata

# Какие схемы мигрируем (служебную alembic_version держим в public)
SCHEMAS = {"users", "scales", "vitals"}

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _get_sync_url() -> str:
    """
    Вернёт СИНХРОННЫЙ URL для Alembic.
    1) Берём из alembic.ini, но игнорируем заглушки типа 'driver_not_used'.
    2) Иначе берём из окружения: DATABASE_URL или APP_DATABASE_URL.
    3) Принудительно заменяем +asyncpg -> +psycopg.
    """
    url = (context.config.get_main_option("sqlalchemy.url") or "").strip()

    placeholders = {"driver_not_used", "DRIVER_NOT_USED", "placeholder", ""}
    if url in placeholders:
        url = os.getenv("DATABASE_URL") or os.getenv("APP_DATABASE_URL") or ""

    if not url:
        raise RuntimeError(
            "No valid sqlalchemy.url found. "
            "Set DATABASE_URL/APP_DATABASE_URL in .env(.test) or alembic.ini."
        )

    # Alembic нужен синхронный драйвер
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg")

    return url


def include_object(object_, name, type_, reflected, compare_to):
    """Фильтруем объекты: только наши схемы; alembic_version оставляем в public."""
    if type_ == "table":
        schema = getattr(object_, "schema", None)
        ctx = context.get_context()
        if schema is None:
            return name == ctx.version_table  # allow alembic_version in public
        return schema in SCHEMAS
    return True

# ------------------------------------------------------------------------------
# Offline mode
# ------------------------------------------------------------------------------

def run_migrations_offline() -> None:
    url = _get_sync_url()
    config.set_main_option("sqlalchemy.url", url)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="public",
        include_object=include_object,
        compare_type=True,
        literal_binds=True,
    )

    with context.begin_transaction():
        context.run_migrations()

# ------------------------------------------------------------------------------
# Online mode
# ------------------------------------------------------------------------------

def run_migrations_online() -> None:
    url = _get_sync_url()
    config.set_main_option("sqlalchemy.url", url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # 1) Гарантируем наличие схем (как «папок» в БД)
        for schema in ("users", "scales", "vitals"):
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

        # 2) Конфигурируем контекст миграций
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="public",
            include_object=include_object,
            compare_type=True,
        )

        # 3) Запускаем миграции
        with context.begin_transaction():
            context.run_migrations()

# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
