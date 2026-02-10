# scripts/init_db_from_models.py
import asyncio
from sqlalchemy import text

from core.db.engine import engine as async_engine
from app.models import Base # где собраны все модели (users, vitals, scales)


# инициализация схем и таблиц по текущим моделям
async def init_db() -> None:
    async with async_engine.begin() as conn:
        # создаём схемы
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS users'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS scales'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS vitals'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS education'))

        # создаём *все* таблицы из моделей
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(init_db())
