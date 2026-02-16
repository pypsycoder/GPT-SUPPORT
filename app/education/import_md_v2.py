# ============================================
# Education Import v2: Импорт уроков из Markdown
# ============================================
# Изменения по сравнению с v1:
#   - card_type теперь per-card, берётся из заголовка ## [type] Заголовок
#   - actions-карточки: строки > ... парсятся в actions_json (JSON-массив)
#   - возвращает List[CardData] вместо List[str]
#
# Поддерживаемые типы карточек:
#   [recognition]  — узнавание ситуации
#   [mechanism]    — объяснение механизма
#   [empowerment]  — что у пациента уже есть
#   [deepdive]     — углубление в тему
#   [actions]      — варианты действий (строки > парсятся в JSON)
#   [anchor]       — якорь к трекеру/разделу платформы
#   (без тега)     — "text", как было в v1, для обратной совместимости
#
# Формат md-файла:
#   # Заголовок урока (emoji опционально)
#
#   ## [recognition] Первая карточка
#   Текст карточки...
#
#   ## [actions] Попробуйте одно из этого
#   > Вариант действия 1
#   > Вариант действия 2
#   > Вариант действия 3

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.education.models import Lesson, LessonCard


# =========================
#  КОНСТАНТЫ
# =========================

VALID_CARD_TYPES = {
    "recognition",
    "mechanism",
    "empowerment",
    "deepdive",
    "actions",
    "anchor",
    "text",  # обратная совместимость
}

# Regex: ## [type] Заголовок карточки
CARD_TYPE_RE = re.compile(r"^\[(\w+)\]\s*(.+)$")

# Regex: строки вариантов действий —  > Текст варианта
ACTION_LINE_RE = re.compile(r"^>\s*(.+)$")


# =========================
#  СТРУКТУРА ДАННЫХ
# =========================

@dataclass
class CardData:
    card_type: str
    title: str
    content_md: str
    actions_json: Optional[str] = None  # JSON-строка, только для [actions]


# =========================
#  ПАРСИНГ
# =========================

def _parse_card_type_and_title(heading_line: str) -> tuple[str, str]:
    """
    '## [recognition] После диализа хочется чтобы все отстали'
    → ('recognition', 'После диализа хочется чтобы все отстали')

    '## Просто заголовок без типа'
    → ('text', 'Просто заголовок без типа')
    """
    # Убираем ## и пробелы
    stripped = heading_line.lstrip("#").strip()
    m = CARD_TYPE_RE.match(stripped)
    if m:
        raw_type = m.group(1).lower()
        title = m.group(2).strip()
        if raw_type not in VALID_CARD_TYPES:
            # Неизвестный тип — не ломаемся, помечаем как text
            return "text", stripped
        return raw_type, title
    return "text", stripped


def _parse_actions(lines: List[str]) -> tuple[str, Optional[str]]:
    """
    Из списка строк карточки [actions] выделяет:
    - content_md: весь текст карточки (без строк >)
    - actions_json: JSON-массив строк из строк вида "> Вариант"

    Строки > могут быть в любом месте блока — парсер их вытащит.
    """
    action_items: List[str] = []
    content_lines: List[str] = []

    for line in lines:
        m = ACTION_LINE_RE.match(line)
        if m:
            action_items.append(m.group(1).strip())
        else:
            content_lines.append(line)

    # Чистим пустые строки по краям content
    while content_lines and not content_lines[0].strip():
        content_lines.pop(0)
    while content_lines and not content_lines[-1].strip():
        content_lines.pop()

    content_md = "\n".join(content_lines).strip()
    actions_json = json.dumps(action_items, ensure_ascii=False) if action_items else None

    return content_md, actions_json


def parse_lesson_markdown(md_text: str) -> List[CardData]:
    """
    Парсит md-файл урока по заголовкам ## и возвращает список CardData.

    Заголовок # (первый уровень) игнорируется — это title урока,
    он передаётся отдельно при импорте.
    """
    lines = md_text.splitlines()
    blocks: List[tuple[str, List[str]]] = []  # (heading_line, content_lines)
    current_heading: Optional[str] = None
    current_block: List[str] = []

    for line in lines:
        if line.strip().startswith("## "):
            if current_heading is not None:
                blocks.append((current_heading, current_block))
            current_heading = line.strip()
            current_block = []
        elif line.strip().startswith("# "):
            # Заголовок урока — пропускаем
            continue
        else:
            if current_heading is not None:
                current_block.append(line)

    if current_heading is not None:
        blocks.append((current_heading, current_block))

    cards: List[CardData] = []

    for heading_line, block_lines in blocks:
        # Убираем пустые строки по краям блока
        while block_lines and not block_lines[0].strip():
            block_lines.pop(0)
        while block_lines and not block_lines[-1].strip():
            block_lines.pop()

        card_type, title = _parse_card_type_and_title(heading_line)

        if card_type == "actions":
            content_md, actions_json = _parse_actions(block_lines)
        else:
            content_md = "\n".join(block_lines).strip()
            actions_json = None

        if not content_md and not actions_json:
            continue  # пустая карточка — пропускаем

        cards.append(CardData(
            card_type=card_type,
            title=title,
            content_md=content_md,
            actions_json=actions_json,
        ))

    return cards


# =========================
#  ИМПОРТ ОДНОГО УРОКА
# =========================

def extract_lesson_code_from_filename(path: Path) -> str:
    """stress_intro.md → 'stress_intro'"""
    return path.stem


async def import_lesson_from_md(
    session: AsyncSession,
    md_path: Path,
    *,
    lesson_code: str,
    topic: str,
    title: str,
    short_description: Optional[str] = None,
) -> Lesson:
    """
    Импортирует урок из md-файла.
    Если урок с таким code уже существует — удаляет старые карточки и создаёт новые.
    card_type берётся per-card из заголовка ## [type].
    actions_json заполняется автоматически для карточек типа [actions].
    """
    md_path = Path(md_path)
    if not md_path.exists():
        raise FileNotFoundError(f"Файл урока не найден: {md_path}")

    md_text = md_path.read_text(encoding="utf-8")
    cards_data = parse_lesson_markdown(md_text)

    if not cards_data:
        raise ValueError(f"В {md_path} нет ни одной карточки '## '.")

    # Ищем существующий урок
    result = await session.execute(
        select(Lesson).where(Lesson.code == lesson_code)
    )
    lesson: Lesson | None = result.scalar_one_or_none()

    if lesson is None:
        lesson = Lesson(
            code=lesson_code,
            topic=topic,
            title=title,
            short_description=short_description,
            order_index=0,
            is_active=True,
        )
        session.add(lesson)
        await session.flush()
    else:
        lesson.topic = topic
        lesson.title = title
        lesson.short_description = short_description
        # Удаляем старые карточки перед перезаписью
        await session.execute(
            delete(LessonCard).where(LessonCard.lesson_id == lesson.id)
        )

    # Создаём карточки
    for idx, card in enumerate(cards_data, start=1):
        lesson_card = LessonCard(
            lesson_id=lesson.id,
            order_index=idx,
            card_type=card.card_type,
            content_md=card.content_md,
            # actions_json добавляем только если поле есть в модели
            # если нет — раскомментируйте после добавления колонки:
            actions_json=card.actions_json,
        )
        session.add(lesson_card)

    await session.commit()
    await session.refresh(lesson)

    return lesson


# =========================
#  ИМПОРТ ПАПКИ
# =========================

async def import_all_lessons_from_folder(
    session: AsyncSession,
    folder: Path,
    *,
    topic: str,
    default_title: str = "",
    default_short: Optional[str] = None,
) -> List[Lesson]:
    """
    Импортирует все *.md файлы из папки как отдельные уроки.
    Сортирует файлы по имени (01_stress.md < 02_emocii.md и т.д.).
    """
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"Папка {folder} не существует.")

    lessons: List[Lesson] = []
    md_files = sorted(folder.glob("*.md"))

    for md_file in md_files:
        code = extract_lesson_code_from_filename(md_file)
        title = default_title or code.replace("_", " ").title()

        lesson = await import_lesson_from_md(
            session=session,
            md_path=md_file,
            lesson_code=code,
            topic=topic,
            title=title,
            short_description=default_short,
        )
        lessons.append(lesson)

    return lessons


# =========================
#  УТИЛИТА: ВАЛИДАЦИЯ MD-ФАЙЛА
# =========================

def validate_lesson_md(md_path: Path) -> dict:
    """
    Проверяет md-файл перед импортом.
    Возвращает словарь с результатами валидации.

    Использование:
        result = validate_lesson_md(Path("01_stress.md"))
        if result["ok"]:
            print(f"Готово: {result['card_count']} карточек")
        else:
            print(result["errors"])
    """
    md_path = Path(md_path)
    errors: List[str] = []
    warnings: List[str] = []

    if not md_path.exists():
        return {"ok": False, "errors": [f"Файл не найден: {md_path}"]}

    md_text = md_path.read_text(encoding="utf-8")
    cards = parse_lesson_markdown(md_text)

    if not cards:
        errors.append("Нет ни одной карточки (заголовков ## )")

    type_counts: dict[str, int] = {}
    for card in cards:
        type_counts[card.card_type] = type_counts.get(card.card_type, 0) + 1

        # Проверяем actions-карточки
        if card.card_type == "actions":
            if not card.actions_json:
                warnings.append(
                    f"Карточка [actions] '{card.title}' не содержит строк '> ...'"
                )
            else:
                items = json.loads(card.actions_json)
                if len(items) < 3:
                    warnings.append(
                        f"Карточка [actions] '{card.title}': "
                        f"рекомендуется 3–4 варианта, найдено {len(items)}"
                    )

    # Проверяем наличие обязательных типов
    recommended = {"recognition", "actions", "anchor"}
    missing = recommended - set(type_counts.keys())
    if missing:
        warnings.append(f"Рекомендуемые типы карточек отсутствуют: {missing}")

    return {
        "ok": len(errors) == 0,
        "card_count": len(cards),
        "type_counts": type_counts,
        "errors": errors,
        "warnings": warnings,
    }
