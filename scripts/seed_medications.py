"""
Заполнить справочник препаратов (medication_references).

Запуск из корня проекта (с активированным venv):
    python scripts/seed_medications.py

Выполнять после применения миграции medications (20260211_02).
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.medications.seed import seed_medication_references  # noqa: E402
from core.db.session import async_session_factory  # noqa: E402


async def main() -> None:
    async with async_session_factory() as session:
        added = await seed_medication_references(session)
        await session.commit()
        print(f"Добавлено записей в справочник препаратов: {added}")


if __name__ == "__main__":
    asyncio.run(main())
