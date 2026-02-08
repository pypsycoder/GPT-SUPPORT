"""
Direct table creation using SQLAlchemy metadata.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from core.db.engine import engine
from app.models import Base


async def create_tables():
    async with engine.begin() as conn:
        # Create schemas
        for schema in ("users", "scales", "vitals", "education"):
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        
        # Create all tables from ORM models
        await conn.run_sync(Base.metadata.create_all)
        print("[OK] All tables created successfully")


if __name__ == "__main__":
    asyncio.run(create_tables())
