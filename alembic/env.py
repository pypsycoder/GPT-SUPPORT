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
from datetime import datetime as _dt


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
import app.sleep_tracker.models  # noqa: F401
import app.medications.models  # noqa: F401
import app.models.llm  # noqa: F401

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
# Revision ID: дата вместо хеша (YYYYMMDD_NN)
# ------------------------------------------------------------------------------

def process_revision_directives(context, revision, directives):
    """
    Генерирует revision_id вида YYYYMMDD_NN вместо случайного хеша.
    Например: 20260216_01, 20260216_02 и т.д.
    Берёт максимальный существующий номер за день и увеличивает на 1.
    """
    if not directives:
        return

    migration_script = directives[0]
    date_str = _dt.now().strftime("%Y%m%d")

    from alembic.script import ScriptDirectory
    script_dir = ScriptDirectory.from_config(context.config)

    # Собираем номера существующих ревизий за сегодня
    existing_nums = []
    for s in script_dir.walk_revisions():
        if s.revision and s.revision.startswith(date_str + "_"):
            try:
                num = int(s.revision.split("_")[1])
                existing_nums.append(num)
            except (IndexError, ValueError):
                pass

    idx = max(existing_nums, default=0) + 1
    migration_script.rev_id = f"{date_str}_{idx:02d}"


# ------------------------------------------------------------------------------
# Фильтр схем для autogenerate
# ------------------------------------------------------------------------------

# Только эти схемы участвуют в autogenerate.
# Всё остальное (системные схемы, сторонние таблицы) — игнорируется.
_MANAGED_SCHEMAS = {"public", "users", "scales", "vitals", "education", "sleep", "practices", "llm"}


def include_object(object, name, type_, reflected, compare_to):
    """
    Ограничивает autogenerate только управляемыми схемами.
    Исключает: alembic_version, cross-schema FK (known autogenerate limitation).
    """
    # Служебная таблица alembic
    if type_ == "table" and name == "alembic_version":
        return False

    # FK между разными схемами autogenerate не умеет сравнивать корректно —
    # всегда генерирует ложный drop+create. Пишем FK руками в миграциях.
    if type_ == "foreign_key_constraint":
        return False

    schema = getattr(object, "schema", None)
    if schema is not None and schema not in _MANAGED_SCHEMAS:
        return False
    return True


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
        include_object=include_object,
        process_revision_directives=process_revision_directives,
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
    # region agent log
    try:
        with (BASE_DIR / "debug-88164a.log").open("a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "88164a",
                        "runId": "pre-fix",
                        "hypothesisId": "H3",
                        "location": "alembic/env.py:run_migrations_online",
                        "message": "entered online migration setup",
                        "data": {"has_url": bool(url), "script_location": config.get_main_option("script_location")},
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
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

        # создаём схемы и сразу коммитим — отдельно от миграций
        for schema in ("users", "scales", "vitals", "llm"):
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            version_table="alembic_version",
            version_table_schema="public",
            include_object=include_object,
            process_revision_directives=process_revision_directives,
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
