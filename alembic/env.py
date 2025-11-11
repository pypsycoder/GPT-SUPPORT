"""Настройка окружения Alembic для проекта."""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# --- пути и .env ---
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# грузим .env из корня
load_dotenv(os.path.join(BASE_DIR, ".env"))

# --- модели проекта ---
from app.models import Base
import app.users.models  # noqa: F401
import app.scales.models  # noqa: F401
# import app.vitals.models  # noqa: F401  # на будущее

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

SCHEMAS = {"users", "scales"}  # потом добавим "vitals"


def get_database_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL не найден. Добавь его в .env или в переменные окружения."
        )
    return db_url


def include_object(object_, name, type_, reflected, compare_to):
    """Фильтруем таблицы по схемам и пропускаем служебную alembic_version."""
    if type_ == "table":
        schema = getattr(object_, "schema", None)
        current_ctx = context.get_context()
        if schema is None:
            # пропускаем служебную таблицу alembic_version в public
            return name == current_ctx.version_table
        return schema in SCHEMAS
    return True


def run_migrations_offline() -> None:
    url = get_database_url()
    config.set_main_option("sqlalchemy.url", url)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="public",
        include_object=include_object,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_database_url()
    config.set_main_option("sqlalchemy.url", url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="public",
            include_object=include_object,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
