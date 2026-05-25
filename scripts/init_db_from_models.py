import asyncio

from app.core.config import load_environment


load_environment()

from core.db.engine import engine
from core.db.init import ensure_database_schemas


async def init_db() -> None:
    await ensure_database_schemas(engine)
    print("[OK] Database schemas are ready. Run `alembic upgrade head` to apply tables and migrations.")


if __name__ == "__main__":
    asyncio.run(init_db())
