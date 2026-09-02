"""
Импорт практик из content/practice/practices_*.md в БД.

Формат файла: один md-файл на блок, практики разделены заголовками
`## П-NNN · тема · тип`. Тело каждой практики — вложенный блок ```markdown ... ```.

Идентификатор практики берётся из заголовка `## П-NNN` (NNN — трёхзначный,
первая цифра = блок: 1NN психология / 2NN гемодиализ / 3NN сквозной) и кладётся
в БД как `pNNN`. Поле **Модуль** внутри блока указывает на урок практики и
хранится строкой ('101', '202', ...).

Запуск:
    python scripts/import_practices.py                      # все три файла блоков
    python scripts/import_practices.py path/to/practices_x.md
    python scripts/import_practices.py path/to/dir/          # все practices_*.md в папке
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import asyncio
import re
from typing import Optional

from app.core.config import load_environment
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker


load_environment()

from core.db.engine import engine as async_engine
from app.practices.models import StandalonePractice as Practice


# ============================================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

# Regex для пар «заголовок практики ## П-NNN … » + следующий блок ```markdown ... ```
# NNN — трёхзначный шифр; тело практики идёт первым ```markdown после заголовка.
PRACTICE_BLOCK_RE = re.compile(
    r"^##\s*П-(?P<num>\d{3})\b[^\n]*\n"       # заголовок ## П-NNN · тема · тип
    r"(?P<between>(?:(?!^##\s).)*?)"           # html-комментарий/пустые строки, но не следующий ##
    r"```markdown\s*\n(?P<body>.*?)\n```",     # тело практики
    re.DOTALL | re.MULTILINE,
)

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


def parse_practice_block(md: str, practice_id: str) -> dict:
    """
    Парсит один markdown-блок практики.
    `practice_id` — шифр из заголовка `## П-NNN`, приведённый к виду `pNNN`.
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
    if not re.fullmatch(r"[123]\d{2}", module_id):
        raise ValueError(
            f"Поле 'Модуль' практики '{title}' = {module_id!r}, ожидался трёхзначный "
            f"код 1NN/2NN/3NN"
        )
    # module_id хранится строкой ('101', '202'); фиксированная ширина сортируется корректно
    if module_id[0] != practice_id[1]:
        raise ValueError(
            f"Блок практики {practice_id!r} и её Модуль {module_id!r} из разных блоков"
        )

    practice_type = fields.get("тип", "").strip()
    if not practice_type:
        raise ValueError(f"Не найдено поле 'Тип' в практике '{title}'")

    icf_domain = fields.get("icf") or None
    context = fields.get("контекст") or None

    # --- Technique metadata ---
    emotion_tags_raw = fields.get("эмоции") or ""
    emotion_tags = [e.strip() for e in emotion_tags_raw.split(",") if e.strip()] or None

    arousal_level = (fields.get("возбуждение") or "").strip() or None

    dialysis_raw = (fields.get("диализ") or "").strip().lower()
    dialysis_ok: Optional[bool] = True if dialysis_raw == "да" else (False if dialysis_raw == "нет" else None)

    mechanism = (fields.get("механизм") or "").strip() or None

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
        "emotion_tags": emotion_tags,
        "arousal_level": arousal_level,
        "dialysis_ok": dialysis_ok,
        "mechanism": mechanism,
    }


# ============================================================
#  ИМПОРТ В БД
# ============================================================

def parse_practice_file(source_file: Path) -> tuple[list[dict], int]:
    """Парсит один md-файл блока → (список практик, число ошибок парсинга)."""
    md_content = source_file.read_text(encoding="utf-8")

    matches = list(PRACTICE_BLOCK_RE.finditer(md_content))
    if not matches:
        print(f"  [WARN] {source_file.name}: не найдено ни одной пары '## П-NNN' + ```markdown")
        return [], 0

    parsed: list[dict] = []
    parse_errors = 0
    for m in matches:
        num = m.group("num")
        practice_id = f"p{num}"
        try:
            data = parse_practice_block(m.group("body"), practice_id)
            parsed.append(data)
            print(f"  OK: {data['id']} (модуль {data['module_id']}) — {data['title']}")
        except ValueError as e:
            print(f"  ОШИБКА парсинга П-{num}: {e}")
            parse_errors += 1
    return parsed, parse_errors


async def import_practices(source_files: list[Path]) -> None:
    """Основная функция импорта: читает файлы блоков, парсит, делает upsert в БД."""
    missing = [f for f in source_files if not f.is_file()]
    if missing:
        for f in missing:
            print(f"[ERROR] Файл не найден: {f}")
        sys.exit(1)

    parsed: list[dict] = []
    parse_errors = 0
    for source_file in source_files:
        print(f"[INFO] {source_file}")
        file_parsed, file_errors = parse_practice_file(source_file)
        parsed.extend(file_parsed)
        parse_errors += file_errors

    # Коллизии id между файлами — фатально: id обязан быть уникален по всей схеме
    seen: dict[str, str] = {}
    for data in parsed:
        if data["id"] in seen:
            print(f"[ERROR] Дубль id {data['id']}: '{seen[data['id']]}' и '{data['title']}'")
            sys.exit(1)
        seen[data["id"]] = data["title"]

    print(f"[INFO] Всего практик распознано: {len(parsed)}")

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


DEFAULT_PRACTICE_DIR = PROJECT_ROOT / "content" / "practice"


def _resolve_sources(raw: Optional[str]) -> list[Path]:
    """None → все practices_*.md в content/practice; путь-папка → practices_*.md в ней; путь-файл → он."""
    if raw is None:
        return sorted(DEFAULT_PRACTICE_DIR.glob("practices_*.md"))
    p = Path(raw)
    if p.is_dir():
        return sorted(p.glob("practices_*.md"))
    return [p]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Импорт практик из content/practice/practices_*.md в БД"
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Путь к md-файлу блока или папке с practices_*.md "
             "(по умолчанию: все три файла в content/practice/)",
    )
    args = parser.parse_args()

    sources = _resolve_sources(args.file)
    if not sources:
        print("[ERROR] Не найдено ни одного файла practices_*.md")
        sys.exit(1)
    asyncio.run(import_practices(sources))


if __name__ == "__main__":
    main()
