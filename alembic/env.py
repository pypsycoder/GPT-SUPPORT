"""Настройка окружения Alembic для проекта."""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from app.models import Base
import app.users.models  # noqa: F401
import app.scales.models  # noqa: F401

# Этот блок считывает настройки логирования Alembic из ini-файла.
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Целевое метаданные — общая база моделей, чтобы автогенерация видела все таблицы.
target_metadata = Base.metadata

# Схемы, с которыми должны работать миграции.
SCHEMAS = {"users", "scales"}


def get_database_url() -> str:
    """Возвращает URL подключения к базе из переменной окружения."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Переменная окружения DATABASE_URL должна быть задана для миграций."
        )
    return database_url


def include_object(object_, name, type_, reflected, compare_to):
    """Фильтрует объекты, оставляя только нужные схемы или служебные таблицы."""

    if type_ == "table":
        schema = getattr(object_, "schema", None)
        if schema is None:
            return name == context.version_table
        return schema in SCHEMAS
    return True


def configure_context(config_section):
    """Применяет общие настройки для контекста миграций."""

    context.configure(
        config_section=config_section,
        target_metadata=target_metadata,
        compare_type=True,
        include_schemas=True,
        version_table_schema="public",
        include_object=include_object,
    )


def run_migrations_offline() -> None:
    """Выполняет миграции в офлайн-режиме без соединения с БД."""

    url = get_database_url()
    config.set_main_option("sqlalchemy.url", url)
    configure_context(config.get_section(config.config_ini_section))

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Выполняет миграции в онлайне, создавая подключение к БД."""

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
            compare_type=True,
            include_schemas=True,
            version_table_schema="public",
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
