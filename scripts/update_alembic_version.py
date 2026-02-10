#!/usr/bin/env python3
"""
Скрипт для отладки и исправления alembic версий
"""

import asyncio
from sqlalchemy import text, create_engine
from core.db.engine import DATABASE_URL

def sync_db_command():
    """Выполнить команду через sync engine"""
    sync_url = DATABASE_URL.replace('asyncpg', 'psycopg')
    engine = create_engine(sync_url)
    
    try:
        with engine.connect() as conn:
            print("\n=== Current alembic versions ===")
            result = conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
            versions = result.fetchall()
            for v in versions:
                print(f"  {v[0]}")
            
            # Проверяем, есть ли уженовая версия
            has_new = any(v[0] == 'f1a2b3c4d5e6' for v in versions)
            if not has_new:
                print("\n=== Inserting new migration version ===")
                conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('f1a2b3c4d5e6')"))
                conn.commit()
                print("[OK] Inserted f1a2b3c4d5e6")
                
                result = conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
                versions = result.fetchall()
                print("\n=== Versions after update ===")
                for v in versions:
                    print(f"  {v[0]}")
            else:
                print("[OK] New version already present")
                
    finally:
        engine.dispose()

if __name__ == "__main__":
    sync_db_command()
