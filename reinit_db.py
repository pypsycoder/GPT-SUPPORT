#!/usr/bin/env python
"""
Скрипт для очистки и переинициализации БД.
"""

import sys
import asyncio
sys.path.insert(0, '.')

from app.models import Base
from core.db.engine import engine

async def reinit_db():
    """Drop all tables and recreate them."""
    async with engine.begin() as conn:
        print("[*] Dropping all existing tables...")
        # Drop all tables in reverse order (respecting foreign key dependencies)
        await conn.run_sync(Base.metadata.drop_all)
        
        print("[*] Creating all tables from models...")
        # Create all tables defined in Base.metadata
        await conn.run_sync(Base.metadata.create_all)
        
        # List created tables
        def list_tables(sync_conn):
            tables = list(Base.metadata.tables.values())
            print(f"[OK] Database reinitialized successfully!")
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
    print("[*] Reinitializing PostgreSQL database from SQLAlchemy models...")
    print(f"[*] Using database: {engine.url}")
    print("[!] WARNING: This will DROP ALL EXISTING TABLES!")
    
    try:
        asyncio.run(reinit_db())
        print("\n[OK] All done!")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
