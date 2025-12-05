# app/education/import_md.py

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.education.models import Lesson, LessonCard


# =========================
#  UTILS
# =========================

def extract_lesson_code_from_filename(path: Path) -> str:
    """
    Файл stress_intro.md → lesson_code = "stress_intro".
    """
    return path.stem  # имя файла без .md


# parse_lesson_markdown
# Делит md-файл по заголовкам "## "
def parse_lesson_markdown(md_text: str) -> List[str]:
    lines = md_text.splitlines()
    cards: List[List[str]] = []
    current_block: List[str] = []

    for line in lines:
        if line.strip().startswith("## "):
            if current_block:
                cards.append(current_block)
                current_block = []
            current_block.append(line)
        else:
            if current_block:
                current_block.append(line)

    if current_block:
        cards.append(current_block)

    # Чистим пустые строки и склеиваем
    card_texts: List[str] = []
    for block in cards:
        while block and not block[0].strip():
            block.pop(0)
        while block and not block[-1].strip():
            block.pop()
        card_md = "\n".join(block).strip()
        if card_md:
            card_texts.append(card_md)

    return card_texts


# =========================
#   IMPORT SINGLE LESSON
# =========================

async def import_lesson_from_md(
    session: AsyncSession,
    md_path: Path,
    *,
    lesson_code: str,
    topic: str,
    title: str,
    short_description: Optional[str] = None,
    card_type: str = "text",
) -> Lesson:

    md_path = Path(md_path)
    if not md_path.exists():
        raise FileNotFoundError(f"Файл урока не найден: {md_path}")

    md_text = md_path.read_text(encoding="utf-8")
    card_texts = parse_lesson_markdown(md_text)

    if not card_texts:
        raise ValueError(f"В {md_path} нет ни одной карточки '##'.")

    # Проверяем существование урока
    result = await session.execute(
        select(Lesson).where(Lesson.code == lesson_code)
    )
    lesson: Lesson | None = result.scalar_one_or_none()

    # Создаём или обновляем Lesson
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
        await session.flush()  # нужен id
    else:
        lesson.topic = topic
        lesson.title = title
        lesson.short_description = short_description

        # Удаляем старые карточки
        await session.execute(
            delete(LessonCard).where(LessonCard.lesson_id == lesson.id)
        )

    # Создаём карточки
    for idx, card_md in enumerate(card_texts, start=1):
        card = LessonCard(
            lesson_id=lesson.id,
            order_index=idx,
            card_type=card_type,
            content_md=card_md,
        )
        session.add(card)

    await session.commit()
    await session.refresh(lesson)

    return lesson


# =========================
#   IMPORT ALL LESSONS IN FOLDER
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
    Импортирует все файлы *.md из папки как отдельные Lesson.

    Для каждого файла:
        stress_intro.md → lesson_code="stress_intro"
        title → default_title или название по файлу
        short → default_short
    """

    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"Папка {folder} не существует.")

    lessons: List[Lesson] = []

    md_files = list(folder.glob("*.md"))
    md_files.sort()

    for md_file in md_files:
        code = extract_lesson_code_from_filename(md_file)

        # Если заголовок не передан — делаем его из имени файла (красиво)
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
