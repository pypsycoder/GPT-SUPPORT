#!/usr/bin/env python
"""
Скрипт для инициализации БД из SQLAlchemy моделей.
Это используется когда autogenerate работает неправильно.
"""

import sys
import asyncio
sys.path.insert(0, '.')

from app.models import Base
from core.db.engine import engine

async def init_db():
    """Initialize database from SQLAlchemy models."""
    async with engine.begin() as conn:
        # Create all tables defined in Base.metadata
        await conn.run_sync(Base.metadata.create_all)
        
        # List created tables
        def list_tables(sync_conn):
            tables = list(Base.metadata.tables.values())
            print(f"[OK] Database initialized successfully!")
            print(f"[*] Total tables created: {len(tables)}")
            print("\n[*] Tables by schema:")
            
            schemas = {}
            for table in tables:
                schema = table.schema or "public"
                if schema not in schemas:
                    schemas[schema] = []
                schemas[schema].append(table.name)
            
            for schema, tables_list in sorted(schemas.items()):
                print(f"  {schema}:")
                for tbl in sorted(tables_list):
                    print(f"    - {tbl}")
        
        await conn.run_sync(list_tables)

if __name__ == "__main__":
    print("[*] Initializing PostgreSQL database from SQLAlchemy models...")
    print(f"[*] Using database: {engine.url}")
    
    try:
        asyncio.run(init_db())
        print("\n[OK] All done!")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
