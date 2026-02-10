#!/usr/bin/env python3
"""Показать содержимое public.alembic_version (для диагностики миграций)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text, create_engine
from core.db.engine import DATABASE_URL

def main():
    sync_url = DATABASE_URL.replace("+asyncpg", "+psycopg").replace("asyncpg", "psycopg")
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        r = conn.execute(text("SELECT version_num FROM public.alembic_version ORDER BY version_num"))
        rows = r.fetchall()
    print("Содержимое public.alembic_version:")
    for row in rows:
        print(" ", row[0])
    print("Всего строк:", len(rows))
    if len(rows) > 1:
        print("\nВнимание: несколько ревизий. Оставьте одну (a1b2c3d4e5f6), затем выполните alembic upgrade 20260210_01")

if __name__ == "__main__":
    main()
