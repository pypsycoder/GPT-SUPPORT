#!/usr/bin/env python3
"""
Диагностический скрипт для проверки:
1. Текущей версии миграции
2. Наличия колонок в таблице users
3. Наличия таблицы researchers
"""

import asyncio
import sys
from datetime import datetime
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Читаем конфиг БД
from core.db.engine import DATABASE_URL

async def check_migration_status():
    """Проверяем состояние миграций и таблиц"""
    
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    try:
        async with engine.begin() as conn:
            # 1. Проверяем текущую версию миграции из alembic_version
            result = await conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"))
            current_version = result.scalar()
            
            
            print(f"\n=== Current Migration Version ===")
            print(f"Version: {current_version}")
            
            # 2. Проверяем колонки в таблице users
            result = await conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'users' AND table_name = 'users'
                ORDER BY ordinal_position
            """))
            columns = result.fetchall()
            
            print(f"\n=== Columns in users.users ===")
            required_columns = {
                'patient_number': False,
                'pin_hash': False,
                'pin_attempts': False,
                'is_locked': False,
                'consent_given_at': False
            }
            
            existing_columns = [col[0] for col in columns]
            for col in columns:
                print(f"  {col[0]}: {col[1]} (nullable={col[2]})")
            
            
            missing = [c for c in required_columns.keys() if c not in existing_columns]
            if missing:
                print(f"\n[ERROR] Missing columns: {missing}")
            else:
                print(f"\n[OK] All required columns present")
            
            # 3. Проверяем наличие таблицы researchers
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'users' AND table_name = 'researchers'
                )
            """))
            researchers_exists = result.scalar()
            
            print(f"\n=== Researchers Table ===")
            if researchers_exists:
                print("[OK] Table exists")
                result = await conn.execute(text("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'users' AND table_name = 'researchers'
                    ORDER BY ordinal_position
                """))
                for col in result.fetchall():
                    print(f"  {col[0]}: {col[1]}")
            else:
                print("[ERROR] Table does not exist")
            
            
            # Summary
            print(f"\n=== SUMMARY ===")
            print(f"[INFO] Migrations applied up to: {current_version}")
            print(f"[INFO] Users columns: {'OK' if not missing else 'MISSING: ' + str(missing)}")
            print(f"[INFO] Researchers table: {'OK' if researchers_exists else 'MISSING'}")
            
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_migration_status())
