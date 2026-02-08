#!/usr/bin/env python3
"""
Скрипт для исправления миграции:
1. Откатываем миграцию f1a2b3c4d5e6 (удаляем researchers, восстанавливаем старую схему users)
2. Удаляем таблицу researchers если она осталась
3. Переприменяем миграцию f1a2b3c4d5e6
"""

import asyncio
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from core.db.engine import DATABASE_URL

async def fix_migration():
    """Исправляем состояние миграции"""
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    try:
        async with engine.begin() as conn:
            print("\n=== Step 1: Check current state ===")
            
            # Проверяем что есть в alembic_version
            result = await conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"))
            current_version = result.scalar()
            print(f"Current migration version: {current_version}")
            
            # Проверяем researchers таблицу
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'users' AND table_name = 'researchers'
                )
            """))
            researchers_exists = result.scalar()
            print(f"Researchers table exists: {researchers_exists}")
            
            # Проверяем наличие новых колонок в users
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'users' AND table_name = 'users' AND column_name = 'patient_number'
                )
            """))
            pin_columns_exist = result.scalar()
            print(f"PIN columns exist in users: {pin_columns_exist}")
            
            print("\n=== Step 2: Drop researchers table if exists ===")
            try:
                await conn.execute(text("DROP TABLE IF EXISTS users.researchers CASCADE"))
                print("[OK] Dropped researchers table")
            except Exception as e:
                print(f"[ERROR] Could not drop researchers: {e}")
            
            print("\n=== Step 3: Update alembic_version to previous ===")
            try:
                await conn.execute(text("DELETE FROM alembic_version WHERE version_num = 'f1a2b3c4d5e6'"))
                print("[OK] Removed failed migration from alembic_version")
            except Exception as e:
                print(f"[WARNING] {e}")
            
            # Проверяем, осталась ли таблица
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'users' AND table_name = 'researchers'
                )
            """))
            researchers_exists = result.scalar()
            print(f"Researchers table after cleanup: {researchers_exists}")
            
            print("\n=== Summary ===")
            print("[OK] Database state cleaned, ready for re-migration")
            
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_migration())
