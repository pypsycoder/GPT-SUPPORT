"""
CLI-скрипт импорта урока из markdown в БД.

Формат имени файла:
    nn.Название.md

Примеры:
    01.Стресс.md
    02.Эмоции.md
    05.Копинг-стратегии.md

Поведение:
    * nn -> порядковый номер урока (order)
    * Название -> русское название урока
    * slug = translit(Название) -> "stress", "emocii", "koping-strategii"
    * lesson_code = "{nn}_{slug}" -> "01_stress"

Внутри файла:
    * Урок режется на карточки по заголовкам второго уровня "## ..."
    * Каждая "## ..." + последующий текст до следующего "##" = одна карточка.
"""
# --- настройка пути к проекту ---
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# --- конец настройки пути ---

import argparse
import asyncio
import re
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.db.engine import engine as async_engine
from app.education.models import Lesson, LessonCard  # поправь при необходимости


# slugify: транслитерация русского названия в латиницу
def slugify(text: str) -> str:
    """Преобразует русскую строку в URL-дружелюбный slug."""
    mapping = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }

    text = text.lower()
    result = []

    for ch in text:
        if ch in mapping:
            result.append(mapping[ch])
        elif ch.isalnum():
            result.append(ch)
        elif ch in (" ", "-", "_"):
            result.append("-")
        # остальные символы просто выкидываем

    slug = "".join(result)
    # убираем двойные дефисы
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


# parse_filename: достаем номер и русское название из "nn.Название.md" или "nn_Название.md"
def parse_filename(path: Path) -> Tuple[int, str]:
    """Разбирает имя файла формата 'nn.Название.md' или 'nn_Название.md' -> (order, title_ru)."""
    stem = path.stem  # "01.Стресс" или "01_Питание"
    num_part, sep, title_part = stem.partition(".")
    if not sep:
        num_part, sep, title_part = stem.partition("_")
    if not sep:
        raise ValueError(
            f"Ожидаю формат 'nn.Название.md' или 'nn_Название.md', а получил '{path.name}'"
        )

    try:
        order = int(num_part)
    except ValueError:
        raise ValueError(
            f"Первые символы до разделителя должны быть числом (порядок урока): '{path.name}'"
        )

    title_ru = title_part.strip()
    if not title_ru:
        raise ValueError(f"Не смог вытащить русское название из '{path.name}'")

    return order, title_ru


# read_markdown: чтение файла
def read_markdown(path: Path) -> str:
    """Читает содержимое markdown-файла в UTF-8."""
    return path.read_text(encoding="utf-8")


# split_into_cards: режем markdown на карточки по '## '
def split_into_cards(md: str) -> List[str]:
    """
    Делит markdown на карточки.

    Логика:
        * новая карточка начинается с строки, которая начинается с '## '
        * '## ' + последующий текст до следующего '## ' или конца файла
          образуют одну карточку
    """
    lines = md.replace("\r\n", "\n").split("\n")

    cards: List[List[str]] = []
    current: List[str] = []

    for line in lines:
        if line.strip().startswith("## "):
            # если уже что-то собирали — закрываем предыдущую карточку
            if current:
                cards.append(current)
                current = []
            current.append(line)
        else:
            # строки до первого '## ' игнорируем — считаем "шапкой" урока
            if current:
                current.append(line)

    if current:
        cards.append(current)

    # чистим и превращаем каждую карточку в текст
    card_texts: List[str] = []
    for raw_card in cards:
        # убираем пустые строки в начале/конце
        while raw_card and not raw_card[0].strip():
            raw_card.pop(0)
        while raw_card and not raw_card[-1].strip():
            raw_card.pop()
        if raw_card:
            card_texts.append("\n".join(raw_card).strip())

    return card_texts


# get_lesson_title_from_md: пытаемся взять заголовок урока из H1
def get_lesson_title_from_md(md: str) -> str:
    """
    Пытается вытащить название урока из первой строки '# ...'.

    Если не нашли — возвращает пустую строку.
    """
    for line in md.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


async def async_import_lesson(path: Path, block_code: Optional[str] = None) -> None:
    """Импортирует один markdown-файл как урок и набор карточек."""
    print(f"\n[Lesson] {path}")

    if not path.is_file():
        print(f"  [WARN] File not found: {path}")
        return

    order_from_name, title_from_name = parse_filename(path)
    md = read_markdown(path)

    # название урока из H1, если есть
    title_from_h1 = get_lesson_title_from_md(md)
    lesson_title = title_from_h1 or title_from_name

    slug = slugify(lesson_title) or slugify(title_from_name)
    # code — стабильный идентификатор урока (для API и поиска)
    lesson_code = f"{order_from_name:02d}_{slug}"

    print(f"  order: {order_from_name}, title: {lesson_title}, code: {lesson_code}")

    # нарезаем карточки
    card_texts = split_into_cards(md)
    if not card_texts:
        print("  [WARN] No cards (no ## headers).")
        return

    print(f"  cards: {len(card_texts)}")

    async_session = async_sessionmaker(
        async_engine,
        expire_on_commit=False,
    )

    async with async_session() as session:
        # --- ищем существующий урок по code
        existing_lesson = await session.scalar(
            select(Lesson).where(Lesson.code == lesson_code)
        )

        if existing_lesson:
            lesson = existing_lesson
            print(f"  [OK] lesson exists id={lesson.id}, updating...")

            # обновляем ключевые поля (под реальные имена)
            if hasattr(lesson, "title"):
                lesson.title = lesson_title
            if hasattr(lesson, "topic"):
                lesson.topic = slug
            if hasattr(lesson, "code"):
                lesson.code = lesson_code
            if hasattr(lesson, "order_index"):
                lesson.order_index = order_from_name
            if block_code is not None and hasattr(lesson, "block_code"):
                lesson.block_code = block_code

            # старые карточки удаляем
            await session.execute(
                delete(LessonCard).where(LessonCard.lesson_id == lesson.id)
            )
        else:
            print("  [NEW] creating lesson.")
            kwargs = {}

            if hasattr(Lesson, "code"):
                kwargs["code"] = lesson_code
            if hasattr(Lesson, "topic"):
                kwargs["topic"] = slug
            if hasattr(Lesson, "title"):
                kwargs["title"] = lesson_title
            if hasattr(Lesson, "short_description"):
                kwargs["short_description"] = None
            if hasattr(Lesson, "order_index"):
                kwargs["order_index"] = order_from_name
            if hasattr(Lesson, "is_active"):
                kwargs["is_active"] = True
            if block_code is not None and hasattr(Lesson, "block_code"):
                kwargs["block_code"] = block_code

            lesson = Lesson(**kwargs)
            session.add(lesson)
            await session.flush()  # чтобы появился lesson.id

        # --- создаём карточки
        cards: List[LessonCard] = []
        for idx, card_md in enumerate(card_texts, start=1):
            card_kwargs = {
                "lesson_id": lesson.id,
            }

            # порядок карточки
            if hasattr(LessonCard, "order_index"):
                card_kwargs["order_index"] = idx
            elif hasattr(LessonCard, "order"):
                card_kwargs["order"] = idx

            # тип карточки (у тебя в БД явно есть card_type NOT NULL)
            if hasattr(LessonCard, "card_type"):
                card_kwargs["card_type"] = "text"

            # тема (если есть такое поле)
            if hasattr(LessonCard, "topic"):
                card_kwargs["topic"] = slug

            # заголовок карточки (если есть поле title)
            if hasattr(LessonCard, "title"):
                card_title = get_card_title_for_model(card_md)
                card_kwargs["title"] = card_title

            # сам markdown-текст — в content_md (NOT NULL)
            if hasattr(LessonCard, "content_md"):
                card_kwargs["content_md"] = card_md
            elif hasattr(LessonCard, "content"):
                card_kwargs["content"] = card_md

            # флаг активности (если есть)
            if hasattr(LessonCard, "is_active"):
                card_kwargs["is_active"] = True

            cards.append(LessonCard(**card_kwargs))

        session.add_all(cards)
        await session.commit()


    print("  [OK] Import done.")

def get_card_title_for_model(card_md: str) -> str:
    """
    Возвращает заголовок карточки для модели: первая строка '## ...'
    без '##' и лишних **.
    """
    if not card_md:
        return ""
    lines = card_md.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            title = re.sub(r"^\*\*(.+)\*\*$", r"\1", title)
            return title
    return ""


# clear_all_lessons: удалить все уроки (каскадно удалятся карточки, тесты, прогресс)
async def clear_all_lessons() -> None:
    """Удаляет все записи Lesson (каскадно — карточки, тесты, прогресс)."""
    async_session = async_sessionmaker(
        async_engine,
        expire_on_commit=False,
    )
    async with async_session() as session:
        await session.execute(delete(Lesson))
        await session.commit()
        print("\n[OK] Vse uroki udaleny (kaskadno - kartochki, testy, progress).")


# async_main: обрабатываем несколько файлов
async def async_main(paths: List[Path], block_code: Optional[str] = None) -> None:
    """Импортирует один или несколько файлов-уроков последовательно."""
    for path in paths:
        try:
            await async_import_lesson(path, block_code=block_code)
        except Exception as exc:
            print(f"\n[ERROR] {path}: {exc}")


# parse_args: CLI
def parse_args():
    """Парсит аргументы командной строки. Возвращает (paths, block_code, clear)."""
    parser = argparse.ArgumentParser(
        description="Импорт markdown-уроков в БД (education.lessons / lesson_cards)."
    )
    parser.add_argument(
        "--dir",
        dest="directory",
        help="Папка с .md уроками (импортируются все *.md в этой папке, без вложенных).",
    )
    parser.add_argument(
        "--block",
        dest="block_code",
        choices=["psychology", "nephrology"],
        help="Код блока: psychology (Внутренняя опора), nephrology (Жизнь на диализе).",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Перед импортом удалить ВСЕ уроки из БД (карточки, тесты, прогресс — каскадно).",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Пути к .md файлам (например: content/education/psychology/01.Стресс.md)",
    )

    args = parser.parse_args()
    paths: List[Path] = []

    if args.directory:
        base_dir = Path(args.directory).resolve()
        if not base_dir.is_dir():
            parser.error(f"Папка не найдена: {base_dir}")
        for p in sorted(base_dir.glob("*.md")):
            if p.is_file() and re.match(r"^\d+[._]", p.stem):
                paths.append(p)

    for p_str in args.files:
        paths.append(Path(p_str).resolve())

    if not paths:
        parser.error("Укажите --dir с папкой или хотя бы один файл.")
    return paths, args.block_code, args.clear


# entrypoint
if __name__ == "__main__":
    files_to_import, block_code, do_clear = parse_args()

    async def run():
        if do_clear:
            await clear_all_lessons()
        await async_main(files_to_import, block_code=block_code)

    asyncio.run(run())
