#!/usr/bin/env python
"""
Простой скрипт для проверки структуры БД.
"""

import asyncio
from sqlalchemy import text, inspect
from core.db.engine import engine

async def main():
    async with engine.begin() as conn:
        try:
            # Проверим, создана ли схема
            result = await conn.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'scales'"))
            schema_exists = result.fetchone() is not None
            print(f"✓ Schema 'scales' exists: {schema_exists}")
            
            if schema_exists:
                # Проверим, создана ли таблица
                result = await conn.execute(text("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'scales' AND table_name = 'scale_results'
                """))
                table_exists = result.fetchone() is not None
                print(f"✓ Table 'scales.scale_results' exists: {table_exists}")
                
                if table_exists:
                    # Проверим столбцы
                    result = await conn.execute(text("""
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'scales' AND table_name = 'scale_results'
                        ORDER BY ordinal_position
                    """))
                    columns = result.fetchall()
                    print(f"\n✓ Columns in scale_results ({len(columns)}):")
                    for col in columns:
                        col_name, col_type, is_nullable, col_default = col
                        nullable_str = "NULL" if is_nullable == "YES" else "NOT NULL"
                        default_str = f" DEFAULT {col_default}" if col_default else ""
                        print(f"   - {col_name}: {col_type} {nullable_str}{default_str}")
                else:
                    print("⚠ Table does not exist!")
            else:
                print("⚠ Schema does not exist!")
                
            # Проверим, установлено ли расширение uuid-ossp
            result = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'uuid-ossp'"))
            uuid_ext_exists = result.fetchone() is not None
            print(f"\n✓ Extension 'uuid-ossp' exists: {uuid_ext_exists}")
            
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
