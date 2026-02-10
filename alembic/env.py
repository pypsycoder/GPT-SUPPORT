# ============================================
# Alembic Env: Конфигурация миграций БД
# ============================================
# Настройка Alembic для работы с PostgreSQL через asyncpg.
# Поддержка .env, кастомные схемы (users, scales, vitals, education).

"""Alembic environment setup (sync engine, .env support, minimal config)."""
from __future__ import annotations

import os
from logging.config import fileConfig
import json
import time
from urllib.parse import urlparse
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from dotenv import load_dotenv


print("### USING ALEMBIC ENV FILE:", __file__)

# ------------------------------------------------------------------------------
# Paths & .env
# ------------------------------------------------------------------------------


BASE_DIR = Path(__file__).resolve().parents[1]

env_file = os.getenv("ENV_FILE") or ".env"
env_path = BASE_DIR / env_file
if not env_path.exists():
    env_path = BASE_DIR / ".env"

load_dotenv(env_path)

# ------------------------------------------------------------------------------
# Alembic config & logging
# ------------------------------------------------------------------------------
print("### USING .ENV PATH:", env_path)
print("### DATABASE_URL:", os.getenv("DATABASE_URL"))
print("### APP_DATABASE_URL:", os.getenv("APP_DATABASE_URL"))
print("### SYNC_DATABASE_URL:", os.getenv("SYNC_DATABASE_URL"))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# ------------------------------------------------------------------------------
# Project metadata
# ------------------------------------------------------------------------------

from app.models import Base  # noqa
import app.users.models  # noqa: F401
import app.researchers.models  # noqa: F401
import app.scales.models  # noqa: F401
import app.vitals.models  # noqa: F401
import app.dialysis.models  # noqa: F401

target_metadata = Base.metadata

_DEBUG_LOG_PATH = Path(r"d:\PROJECT\GPT-SUPPORT\.cursor\debug.log")


def _debug_log(*, run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    payload = {
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------


def _get_sync_url() -> str:
    """
    Синхронный URL для Alembic:

    1) SYNC_DATABASE_URL
    2) APP_DATABASE_URL
    3) DATABASE_URL

    Если async (postgresql+asyncpg) — меняем на sync (postgresql+psycopg).
    """
    source = None
    url = os.getenv("DATABASE_URL") or ""
    if url:
        source = "DATABASE_URL"
    if not url:
        raise RuntimeError("Нет DATABASE_URL в .env")

    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg")

    parsed = urlparse(url)
    # region agent log
    _debug_log(
        run_id="pre-fix",
        hypothesis_id="H2",
        location="alembic/env.py:_get_sync_url",
        message="resolved sync url metadata",
        data={
            "source": source,
            "driver": parsed.scheme,
            "host": parsed.hostname,
            "port": parsed.port,
            "database": (parsed.path or "").lstrip("/"),
        },
    )
    # endregion

    return url


# ------------------------------------------------------------------------------
# Offline mode
# ------------------------------------------------------------------------------


def run_migrations_offline() -> None:
    url = _get_sync_url()
    config.set_main_option("sqlalchemy.url", url)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        version_table="alembic_version",
        version_table_schema="public",
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ------------------------------------------------------------------------------
# Online mode
# ------------------------------------------------------------------------------

def run_migrations_online() -> None:
    url = _get_sync_url()

    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = url

    # region agent log
    _debug_log(
        run_id="pre-fix",
        hypothesis_id="H2",
        location="alembic/env.py:run_migrations_online",
        message="starting online migration",
        data={"has_url": bool(url)},
    )
    # endregion

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # DEBUG — оставь, он полезный
        result = connection.execute(
            text("SELECT current_database(), inet_server_addr(), inet_server_port()")
        )
        db_name, server_addr, server_port = result.fetchone()
        print(f"\n[ALEMBIC DEBUG] DB={db_name}, host={server_addr}, port={server_port}\n")

        # создаём схемы, НО НЕ ТРОГАЕМ alembic_version
        for schema in ("users", "scales", "vitals"):
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            version_table="alembic_version",
            version_table_schema="public",
        )

        with context.begin_transaction():
            context.run_migrations()

        connection.commit()


# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
