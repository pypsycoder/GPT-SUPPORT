#!/usr/bin/env python3
"""
Скрипт для применения миграции вручную (SQL)
"""

import asyncio
from sqlalchemy import text, create_engine
from core.db.engine import DATABASE_URL

def apply_migration_manually():
    """Выполнить миграцию вручную через SQL"""
    sync_url = DATABASE_URL.replace('asyncpg', 'psycopg')
    engine = create_engine(sync_url)
    
    try:
        with engine.begin() as conn:
            print("\n=== Applying migration manually ===")
            
            # 1. Добавляем колонки в users
            print("\n[1] Adding PIN auth columns to users...")
            try:
                conn.execute(text("""
                    ALTER TABLE users.users
                    ADD COLUMN patient_number INTEGER UNIQUE,
                    ADD COLUMN pin_hash VARCHAR(128),
                    ADD COLUMN pin_attempts INTEGER DEFAULT 0 NOT NULL,
                    ADD COLUMN is_locked BOOLEAN DEFAULT false NOT NULL,
                    ADD COLUMN consent_given_at TIMESTAMP WITH TIME ZONE
                """))
                print("    [OK] Added PIN columns")
            except Exception as e:
                print(f"    [ERROR] {e}")
                return False
            
            # 2. Добавляем индекс для patient_number
            print("\n[2] Adding index for patient_number...")
            try:
                conn.execute(text("""
                    CREATE UNIQUE INDEX ix_users_patient_number 
                    ON users.users (patient_number)
                """))
                print("    [OK] Index created")
            except Exception as e:
                print(f"    [WARNING] {e}")  # Может быть уже создан
            
            # 3. Делаем telegram_id nullable
            print("\n[3] Making telegram_id nullable...")
            try:
                conn.execute(text("""
                    ALTER TABLE users.users
                    ALTER COLUMN telegram_id DROP NOT NULL
                """))
                print("    [OK] telegram_id is now nullable")
            except Exception as e:
                print(f"    [WARNING] {e}")  # Может быть уже nullable
            
            # 4. Создаём таблицу researchers
            print("\n[4] Creating researchers table...")
            try:
                conn.execute(text("""
                    CREATE TABLE users.researchers (
                        id SERIAL NOT NULL,
                        username VARCHAR(50) NOT NULL,
                        password_hash VARCHAR(128) NOT NULL,
                        full_name VARCHAR(255),
                        is_active BOOLEAN DEFAULT true NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                        PRIMARY KEY (id)
                    )
                """))
                print("    [OK] Table created")
            except Exception as e:
                print(f"    [WARNING] {e}")  # Может быть уже создана
            
            # 5. Добавляем индекс для username
            print("\n[5] Adding index for researchers.username...")
            try:
                conn.execute(text("""
                    CREATE UNIQUE INDEX ix_researchers_username
                    ON users.researchers (username)
                """))
                print("    [OK] Index created")
            except Exception as e:
                print(f"    [WARNING] {e}")  # Может быть уже создан
            
            print("\n=== Migration applied successfully ===")
            return True
            
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        return False
    finally:
        engine.dispose()

if __name__ == "__main__":
    success = apply_migration_manually()
    exit(0 if success else 1)
