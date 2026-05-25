import asyncio

from app.core.config import load_environment


load_environment()

from core.db.engine import engine
from core.db.init import ensure_database_schemas


async def create_tables() -> None:
    await ensure_database_schemas(engine)
    print("[OK] Schemas created. Apply structural changes through Alembic migrations.")


if __name__ == "__main__":
    asyncio.run(create_tables())
