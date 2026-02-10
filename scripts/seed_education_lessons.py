"""
Импорт всех уроков из content/education/*.md в БД.

Запуск из корня проекта (с активированным venv):
    python scripts/seed_education_lessons.py

Импортирует только .md в корне content/education/ (не папку tests/).
Формат имён: nn.Название.md (как в import_lesson_from_md.py).
"""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_lesson_from_md import async_main

CONTENT_DIR = PROJECT_ROOT / "content" / "education"


def main():
    md_files = sorted(
        f for f in CONTENT_DIR.iterdir()
        if f.is_file() and f.suffix.lower() == ".md"
    )
    if not md_files:
        print(f"В папке {CONTENT_DIR} не найдено .md файлов.")
        sys.exit(1)
    print(f"Найдено уроков: {len(md_files)}")
    for p in md_files:
        print(f"  - {p.name}")
    asyncio.run(async_main(md_files))
    print("Готово. Обновите страницу «Обучение» в браузере.")


if __name__ == "__main__":
    main()
