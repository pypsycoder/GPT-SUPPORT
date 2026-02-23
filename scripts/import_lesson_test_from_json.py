# ============================================
# Import Lesson Tests: CLI-импорт тестов из JSON/MD
# ============================================
# Парсит файлы формата nn.Название-тест.md, извлекает JSON-массив
# вопросов и создаёт записи LessonTest + LessonTestQuestion в БД.
# Поддерживает импорт отдельных файлов и целых папок.

"""
CLI-скрипт импорта тестов уроков из JSON/MD-файлов в БД.

Формат имени файла:
    nn.Название-тест.md

Примеры:
    01.Стресс-тест.md
    02.Эмоции-тест.md

Поведение:
    * nn -> порядковый номер урока (order)
    * Название-тест -> русское название теста
    * slug = slugify(Название-тест) -> "stress-test"
    * lesson_code_full = "{nn}_{slug}"  -> "01_stress-test"
    * lesson_code_base = "{nn}_{slug_base}", где slug_base = до первого "-" -> "01_stress"
      (это позволит привязать тест "Стресс-тест" к уроку "Стресс")

Внутри файла:
    * содержится JSON-массив вопросов:
        [
          {
            "order_index": 1,
            "question_text": "...",
            "option_1": "...",
            "option_2": "...",
            "option_3": "...",
            "option_4": "...",
            "correct_option": 4
          },
          ...
        ]
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
import json
import re
from typing import List, Tuple, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.db.engine import engine as async_engine
from app.education.models import Lesson, LessonTest, LessonTestQuestion


# ============================================
#   Утилиты (slugify, парсинг имени файла)
# ============================================

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
    slug = re.sub(r"-{2,}", "-", slug)  # убираем двойные дефисы
    return slug.strip("-")


def parse_filename(path: Path) -> Tuple[int, str]:
    """
    Разбирает имя файла формата 'nn.Название.md' или 'nn_Название.md' -> (order, title_ru).
    Аналогично import_lesson_from_md.py.
    """
    stem = path.stem  # "01.Стресс-тест" или "01_Стресс-тест"
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
            f"Первые символы до разделителя должны быть числом (порядок): '{path.name}'"
        )

    title_ru = title_part.strip()
    if not title_ru:
        raise ValueError(f"Не смог вытащить русское название из '{path.name}'")

    return order, title_ru


def guess_lesson_codes(order: int, test_title_ru: str) -> Tuple[Optional[str], Optional[str]]:
    """
    По названию теста пытаемся угадать код урока.

    Пример:
        order = 1, test_title_ru = "Стресс-тест"
        slug_full  = "stress-test"
        lesson_code_full = "01_stress-test"
        slug_base = "stress"
        lesson_code_base = "01_stress"
    """
    slug_full = slugify(test_title_ru)
    lesson_code_full = f"{order:02d}_{slug_full}" if slug_full else None

    slug_base = slug_full.split("-")[0] if slug_full else None
    lesson_code_base = f"{order:02d}_{slug_base}" if slug_base else None

    return lesson_code_full, lesson_code_base


# ============================================
#   Загрузка вопросов из файла
# ============================================

def load_questions_from_file(path: Path) -> List[dict]:
    """
    Загружаем список вопросов из файла.

    Файл может иметь расширение .md, но внутри должен быть JSON-массив объектов:
      - order_index (опционально)
      - question_text
      - option_1..option_4
      - correct_option
    """
    text = path.read_text(encoding="utf-8")

    # На случай, если когда-то в .md будет шапка — ищем первую '['
    first_bracket = text.find("[")
    if first_bracket > 0:
        text = text[first_bracket:]

    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Ожидался JSON-массив вопросов в файле: " + str(path))
    return data


# ============================================
#   Поиск урока в БД
# ============================================

def _lesson_order_for_lookup(order_from_name: int, block_code: Optional[str]) -> int:
    """
    В блоке nephrology тесты могут быть названы 11_, 12_, ... 18_ (соответствуют урокам 1–8).
    Возвращает order_index для поиска урока в БД.
    """
    if block_code == "nephrology" and 11 <= order_from_name <= 18:
        return order_from_name - 10
    return order_from_name


async def find_lesson_for_test(
    session,
    order: int,
    lesson_code_full: Optional[str],
    lesson_code_base: Optional[str],
    block_code: Optional[str] = None,
) -> Lesson:
    """
    Пытаемся найти Lesson для этого теста:
    1) по полному коду (и опционально block_code)
    2) по базовому коду (и опционально block_code)
    3) по order_index + block_code (для nephrology: 11->1, 12->2, ... 18->8)
    """
    order_lookup = _lesson_order_for_lookup(order, block_code)

    def with_block(stmt):
        if block_code is not None and hasattr(Lesson, "block_code"):
            return stmt.where(Lesson.block_code == block_code)
        return stmt

    # 1. полный код
    if lesson_code_full and hasattr(Lesson, "code"):
        stmt = select(Lesson).where(Lesson.code == lesson_code_full)
        lesson = await session.scalar(with_block(stmt))
        if lesson:
            return lesson

    # 2. базовый код
    if lesson_code_base and hasattr(Lesson, "code"):
        stmt = select(Lesson).where(Lesson.code == lesson_code_base)
        lesson = await session.scalar(with_block(stmt))
        if lesson:
            return lesson

    # 3. по order_index (и block_code); для nephrology используем order_lookup (1–8)
    if hasattr(Lesson, "order_index"):
        stmt = select(Lesson).where(Lesson.order_index == order_lookup)
        lesson = await session.scalar(with_block(stmt))
        if lesson:
            return lesson

    raise RuntimeError(
        f"Не смог найти Lesson ни по code='{lesson_code_full}'/'{lesson_code_base}', "
        f"ни по order_index={order_lookup} (from file order {order})"
        + (f" (block_code={block_code})" if block_code else "")
    )


# ============================================
#   Импорт теста в БД
# ============================================

async def async_import_test(path: Path, block_code: Optional[str] = None) -> None:
    """Импортирует один файл как LessonTest + LessonTestQuestion."""
    print(f"\n🧪 Импорт теста из файла: {path}")

    if not path.is_file():
        print(f"  ⚠️  Файл не найден: {path}")
        return

    order_from_name, test_title_ru = parse_filename(path)
    lesson_code_full, lesson_code_base = guess_lesson_codes(order_from_name, test_title_ru)

    print(f"  ➜ order (из имени): {order_from_name}")
    print(f"  ➜ test title (ru):  {test_title_ru}")
    print(f"  ➜ lesson_code full: {lesson_code_full}")
    print(f"  ➜ lesson_code base: {lesson_code_base}")

    questions = load_questions_from_file(path)
    if not questions:
        print("  ⚠️  В файле не найдено ни одного вопроса.")
        return

    print(f"  ➜ загружено вопросов: {len(questions)}")

    async_session = async_sessionmaker(
        async_engine,
        expire_on_commit=False,
    )

    async with async_session() as session:
        # Находим Lesson (с учётом block_code, если передан)
        lesson = await find_lesson_for_test(
            session,
            order_from_name,
            lesson_code_full,
            lesson_code_base,
            block_code=block_code,
        )
        print(f"  ✅ урок найден (id={lesson.id}, code={getattr(lesson, 'code', None)})")

        # Определяем order_index теста: max+1, если есть поле
        next_order_index = None
        if hasattr(LessonTest, "order_index"):
            max_order_res = await session.execute(
                select(func.max(LessonTest.order_index)).where(
                    LessonTest.lesson_id == lesson.id
                )
            )
            max_order = max_order_res.scalar()
            next_order_index = (max_order or 0) + 1

        # ---- Генерируем code для LessonTest ----
        test_code = None
        if hasattr(LessonTest, "code"):
            # пробуем использовать lesson_code_full, например "01_stress-test"
            test_code = lesson_code_full

            # если вдруг не получилось — делаем fallback от lesson.code + slug(test_title)
            if not test_code:
                base = getattr(lesson, "code", None) or f"{order_from_name:02d}"
                test_slug = slugify(test_title_ru)
                if test_slug:
                    test_code = f"{base}_{test_slug}"
                else:
                    test_code = f"{base}_test"

        # Создаём LessonTest
        test_kwargs = {"lesson_id": lesson.id}

        if hasattr(LessonTest, "code") and test_code:
            test_kwargs["code"] = test_code

        if hasattr(LessonTest, "title"):
            # Имя теста — как в имени файла, либо можно сделать "Тест: <lesson.title>"
            test_kwargs["title"] = test_title_ru

        if hasattr(LessonTest, "short_description"):
            test_kwargs["short_description"] = None

        if hasattr(LessonTest, "order_index") and next_order_index is not None:
            test_kwargs["order_index"] = next_order_index

        if hasattr(LessonTest, "is_active"):
            test_kwargs["is_active"] = True

        test = LessonTest(**test_kwargs)
        session.add(test)
        await session.flush()  # получаем test.id

        print(f"  ➕ создан LessonTest id={test.id} для lesson_id={lesson.id}")

        # ===== вставляем вопросы и commit =====
        created = 0
        for idx, raw in enumerate(questions, start=1):
            q_kwargs = {
                "test_id": test.id,
                "question_text": raw["question_text"],
                "option_1": raw["option_1"],
                "option_2": raw["option_2"],
                "option_3": raw["option_3"],
                "option_4": raw["option_4"],
                "correct_option": raw["correct_option"],
            }

            if hasattr(LessonTestQuestion, "order_index"):
                q_kwargs["order_index"] = raw.get("order_index") or idx

            if hasattr(LessonTestQuestion, "is_active"):
                q_kwargs["is_active"] = True

            session.add(LessonTestQuestion(**q_kwargs))
            created += 1

        await session.commit()
        print(f"  ✅ Импорт теста завершён: создано вопросов = {created}")

async def async_main(paths: List[Path], block_code: Optional[str] = None) -> None:
    """Импортирует один или несколько файлов-тестов последовательно."""
    for path in paths:
        try:
            await async_import_test(path, block_code=block_code)
        except Exception as exc:
            print(f"\n❌ Ошибка при импорте '{path}': {exc}")


# ============================================
#   CLI (argparse + main)
# ============================================

def parse_args():
    """Парсит аргументы командной строки. Возвращает (paths, block_code)."""
    parser = argparse.ArgumentParser(
        description="Импорт тестов уроков в БД (education.lesson_tests / lesson_test_questions)."
    )
    parser.add_argument(
        "--dir",
        "--folder",
        dest="directory",
        help="Папка с тестами (например: content/education/psychology/tests)",
    )
    parser.add_argument(
        "--block",
        dest="block_code",
        choices=["psychology", "nephrology"],
        help="Код блока: psychology, nephrology (для поиска урока по order_index+block).",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Пути к .md/.json файлам с тестами (например: content/education/psychology/tests/01_Стресс-тест.md)",
    )

    args = parser.parse_args()
    paths: List[Path] = []

    # Если указана папка — собираем все *.md и *.json в ней (имя: nn_... или nn....)
    if args.directory:
        base_dir = Path(args.directory).resolve()
        if not base_dir.is_dir():
            parser.error(f"Папка не найдена: {base_dir}")

        for pattern in ("*.md", "*.json"):
            for p in sorted(base_dir.glob(pattern)):
                if p.is_file() and re.match(r"^\d+[._]", p.stem):
                    paths.append(p)

    # Плюс явно перечисленные файлы (если есть)
    for p_str in args.files:
        p = Path(p_str).resolve()
        if not p.is_file():
            parser.error(f"Файл не найден: {p}")
        paths.append(p)

    if not paths:
        parser.error("Нужно указать либо --dir с папкой, либо хотя бы один файл.")

    # убираем возможные дубли
    unique_paths: List[Path] = []
    seen = set()
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)

    return unique_paths, args.block_code


if __name__ == "__main__":
    files_to_import, block_code = parse_args()
    asyncio.run(async_main(files_to_import, block_code=block_code))
