# engine.py — инициализация async движка
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/hemo_db"

engine = create_async_engine(DATABASE_URL, echo=True, future=True)
