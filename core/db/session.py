# session.py — сессии для работы с БД
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from .engine import engine

# асинхронный sessionmaker
async_session_factory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Dependency для получения ``AsyncSession``.

    Используется в HTTP-ручках для работы с БД.
    """

    async with async_session_factory() as session:
        yield session
