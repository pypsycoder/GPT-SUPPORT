"""
Импорт практик из practices_block_a.md в БД.

Формат файла: один большой md-файл с практиками, разделёнными ```.
Каждая практика содержит вложенный блок ```markdown ... ```.

Запуск:
    python scripts/import_practices.py [path/to/practices_block_a.md]
    (по умолчанию: content/practice/practices_block_a.md)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import asyncio
import json
import re
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.db.engine import engine as async_engine
from app.practices.models import StandalonePractice as Practice


# ============================================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

# Regex для поиска всех блоков ```markdown ... ```
CODEBLOCK_RE = re.compile(r"```markdown\s*\n(.*?)```", re.DOTALL)

# Regex для полей **Поле:** значение
BOLD_FIELD_RE = re.compile(r"\*\*([^*]+):\*\*\s+(.+)")

# Regex для H1 заголовка
H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# Regex для заголовков секций ## [tagline], ## [instruction], etc.
SECTION_HEADER_RE = re.compile(r"^##\s+\[(\w+)\]\s*$")

# Regex для пронумерованных шагов инструкции
NUMBERED_STEP_RE = re.compile(r"^\d+\.\s+(.+)$")


def strip_emoji(text: str) -> str:
    """Убрать emoji и прочие не-буквенные символы в начале строки."""
    return re.sub(r"^[^\w]+", "", text, flags=re.UNICODE).strip()


def make_practice_id(module_id: str, practice_type: str, raw_title: str) -> str:
    """
    Генерирует стабильный ID практики.

    Логика: берём все цифры из заголовка (до очистки emoji).
    Если суммарная длина >= 2 — добавляем как суффикс.
    Иначе ID = p{module_id}_{type}.

    Примеры:
        '🌬️ 4-7-8: дыхание...' → p01_breathing_478
        '🌿 Заземление 5-4-3-2-1' → p02_body_54321
        '⬛ Квадратное дыхание'   → p03_breathing
    """
    digits = "".join(re.findall(r"\d+", raw_title))
    if len(digits) >= 2:
        return f"p{module_id}_{practice_type}_{digits}"
    return f"p{module_id}_{practice_type}"


def parse_sections(md: str) -> dict[str, str]:
    """
    Разбивает md-блок на именованные секции по заголовкам ## [name].
    Возвращает dict: {'tagline': '...', 'instruction': '...', ...}
    """
    sections: dict[str, str] = {}
    current_name: Optional[str] = None
    current_lines: list[str] = []

    for line in md.split("\n"):
        m = SECTION_HEADER_RE.match(line.strip())
        if m:
            if current_name is not None:
                sections[current_name] = "\n".join(current_lines).strip()
            current_name = m.group(1).lower()
            current_lines = []
        elif current_name is not None:
            current_lines.append(line)

    if current_name is not None:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections


def parse_instruction(instruction_raw: str) -> list[str]:
    """
    Парсит нумерованный список шагов инструкции.
    Многострочные шаги (с продолжением) объединяются через '\\n'.
    """
    steps: list[str] = []
    current_lines: list[str] = []

    for line in instruction_raw.split("\n"):
        m = NUMBERED_STEP_RE.match(line)
        if m:
            if current_lines:
                steps.append("\n".join(current_lines))
            current_lines = [m.group(1).strip()]
        elif current_lines:
            stripped = line.strip()
            if stripped:
                current_lines.append(stripped)

    if current_lines:
        steps.append("\n".join(current_lines))

    return steps


def parse_practice_block(md: str) -> dict:
    """
    Парсит один markdown-блок практики.
    Возвращает dict с полями для таблицы practices.
    Выбрасывает ValueError при ошибке.
    """
    # --- H1 → title ---
    m = H1_RE.search(md)
    if not m:
        raise ValueError("Не найден H1 заголовок")
    raw_title = m.group(1).strip()
    title = strip_emoji(raw_title)
    if not title:
        raise ValueError(f"Пустой заголовок после очистки emoji: {raw_title!r}")

    # --- Поля **Поле:** значение ---
    fields: dict[str, str] = {}
    for fm in BOLD_FIELD_RE.finditer(md):
        key = fm.group(1).strip().lower()
        val = fm.group(2).strip()
        fields[key] = val

    module_id = fields.get("модуль", "").strip()
    if not module_id:
        raise ValueError(f"Не найдено поле 'Модуль' в практике '{title}'")
    # Нормализуем до двузначного с ведущим нулём
    module_id = module_id.zfill(2)

    practice_type = fields.get("тип", "").strip()
    if not practice_type:
        raise ValueError(f"Не найдено поле 'Тип' в практике '{title}'")

    icf_domain = fields.get("icf") or None
    context = fields.get("контекст") or None

    # --- Секции ---
    sections = parse_sections(md)

    tagline = sections.get("tagline", "").strip() or None
    completion_prompt = sections.get("prompt", "").strip() or None

    instruction_raw = sections.get("instruction", "")
    instruction = parse_instruction(instruction_raw)
    if not instruction:
        raise ValueError(f"Пустая инструкция в практике '{title}'")

    timer_raw = sections.get("timer", "0").strip()
    try:
        duration_seconds = int(timer_raw)
    except ValueError:
        duration_seconds = 0

    # --- ID ---
    practice_id = make_practice_id(module_id, practice_type, raw_title)

    return {
        "id": practice_id,
        "module_id": module_id,
        "type": practice_type,
        "icf_domain": icf_domain,
        "context": context,
        "title": title,
        "tagline": tagline,
        "instruction": instruction,
        "duration_seconds": duration_seconds,
        "completion_prompt": completion_prompt,
        "is_active": True,
    }


# ============================================================
#  ИМПОРТ В БД
# ============================================================

async def import_practices(source_file: Path) -> None:
    """Основная функция импорта: читает файл, парсит, делает upsert в БД."""
    if not source_file.is_file():
        print(f"[ERROR] Файл не найден: {source_file}")
        sys.exit(1)

    md_content = source_file.read_text(encoding="utf-8")

    # Найти все вложенные ```markdown блоки
    blocks = CODEBLOCK_RE.findall(md_content)
    if not blocks:
        print("[ERROR] Не найдено ни одного блока ```markdown в файле")
        sys.exit(1)

    print(f"[INFO] Найдено блоков для парсинга: {len(blocks)}")

    # Распарсить каждый блок
    parsed: list[dict] = []
    parse_errors = 0

    for i, block in enumerate(blocks, start=1):
        try:
            data = parse_practice_block(block)
            parsed.append(data)
            print(f"  [{i}] OK: {data['id']} — {data['title']}")
        except ValueError as e:
            print(f"  [{i}] ОШИБКА парсинга: {e}")
            parse_errors += 1

    if not parsed:
        print("[ERROR] Нет успешно распарсенных практик. Выход.")
        sys.exit(1)

    # Upsert в БД
    async_session = async_sessionmaker(async_engine, expire_on_commit=False)

    added = 0
    updated = 0
    db_errors = 0

    async with async_session() as session:
        # Получаем уже существующие ID
        existing_result = await session.execute(select(Practice.id))
        existing_ids = {row[0] for row in existing_result.fetchall()}

        for data in parsed:
            practice_id = data["id"]
            try:
                stmt = pg_insert(Practice.__table__).values(**data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={k: v for k, v in data.items() if k != "id"},
                )
                await session.execute(stmt)

                if practice_id in existing_ids:
                    updated += 1
                else:
                    added += 1

            except Exception as e:
                print(f"  [DB ERROR] {practice_id}: {e}")
                db_errors += 1

        await session.commit()

    total_errors = parse_errors + db_errors
    print(
        f"\n[ИТОГ] добавлено {added} / обновлено {updated} / ошибок {total_errors}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт практик из md-файла в БД")
    parser.add_argument(
        "file",
        nargs="?",
        default=str(PROJECT_ROOT / "content" / "practice" / "practices_block_a.md"),
        help="Путь к md-файлу с практиками",
    )
    args = parser.parse_args()

    asyncio.run(import_practices(Path(args.file)))


if __name__ == "__main__":
    main()
