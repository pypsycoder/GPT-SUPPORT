"""Доступ к ``public.app_settings`` — рантайм-тумблеры админ-панели.

``get_setting`` / ``set_setting`` — тонкая обёртка над ORM. Коммит — за
вызывающим (роутером), как везде в проекте.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_settings import AppSetting

# Ключ переключателя LLM-провайдера (см. app/llm/pool.py).
LLM_PROVIDER_KEY = "llm_provider"


async def get_setting(
    session: AsyncSession, key: str, default: str | None = None
) -> str | None:
    row = await session.get(AppSetting, key)
    return row.value if row is not None else default


async def set_setting(
    session: AsyncSession, key: str, value: str, *, updated_by: str | None = None
) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value, updated_by=updated_by))
    else:
        row.value = value
        row.updated_by = updated_by
    await session.flush()


async def get_setting_row(session: AsyncSession, key: str) -> AppSetting | None:
    return await session.get(AppSetting, key)
