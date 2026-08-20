"""Создание таблиц ORM-моделей в sqlite для тестов.

Тесты поднимают sqlite in-memory и раньше повторяли схему руками через
``CREATE TABLE``. Такой дубль молча расходится с моделью: после появления
``chat_messages.thread_id`` тест падал не на своём предмете, а на INSERT.

Прямой ``Model.__table__.create`` тоже не годится: модели объявляют
``server_default=NOW()`` — валидно для PostgreSQL, но sqlite не понимает вызов
функции в ``DEFAULT``. Поэтому таблица клонируется в отдельную ``MetaData``,
где дефолт заменяется на ``CURRENT_TIMESTAMP``, а внешние ключи снимаются —
sqlite их всё равно не проверяет, а резолвить схему ``users`` при клонировании
одной таблицы не на что.

Схема таблицы (``llm``, ``users``) сохраняется: движок в тестах создаётся с
``schema_translate_map``, который сводит её к ``main``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

# Дефолты, которые PostgreSQL понимает, а sqlite — нет.
_SERVER_DEFAULT_REPLACEMENTS = {"now()": "CURRENT_TIMESTAMP"}


def _adapt_server_defaults(table: sa.Table) -> None:
    for column in table.columns:
        default = column.server_default
        arg = getattr(default, "arg", None)
        if arg is None:
            continue
        replacement = _SERVER_DEFAULT_REPLACEMENTS.get(str(arg).strip().lower())
        if replacement is not None:
            column.server_default = sa.DefaultClause(sa.text(replacement))


def _drop_foreign_keys(table: sa.Table) -> None:
    for constraint in list(table.constraints):
        if isinstance(constraint, sa.ForeignKeyConstraint):
            table.constraints.discard(constraint)
    for column in table.columns:
        column.foreign_keys = set()
    # Порядок создания таблиц считается по table.foreign_keys, а не по
    # constraints, так что чистить нужно обе коллекции.
    table.foreign_keys = set()


def create_tables(connection: Connection, *models: Any) -> None:
    """Создать таблицы переданных моделей в sqlite.

    Вызывается через ``await conn.run_sync(create_tables, User, ChatMessage)``.
    """
    metadata = sa.MetaData()
    tables = []
    for model in models:
        table = model.__table__.to_metadata(metadata)
        _drop_foreign_keys(table)
        _adapt_server_defaults(table)
        tables.append(table)
    metadata.create_all(connection, tables=tables)
