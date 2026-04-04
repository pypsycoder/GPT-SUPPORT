from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


SCHEMA_NAMES = (
    "education",
    "kdqol",
    "llm",
    "medications",
    "practices",
    "scales",
    "sleep",
    "users",
    "vitals",
)


async def ensure_database_schemas(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for schema in SCHEMA_NAMES:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
