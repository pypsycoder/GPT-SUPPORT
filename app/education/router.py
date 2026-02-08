from __future__ import annotations

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.education.models import (
    Lesson,
    LessonCard,
    LessonTest,
    LessonTestQuestion,
    LessonTestResult,
    LessonProgress,
)
from app.auth.dependencies import get_current_user
from app.users.models import User

from app.education.schemas import (
    EducationItem,
    LessonRead,
    LessonCardRead,
    TestInfo,
    TestQuestion,
    TestQuestionsResponse,
    TestSubmitRequest,
    TestSubmitResponse,
    TestResultResponse,
)

from core.db.session import get_async_session


# router_education
# Роутер для работы с обучающими материалами.
router = APIRouter(tags=["education"])


# ====== ВСПОМОГАТЕЛЬНЫЕ КОНСТАНТЫ / ФУНКЦИИ =================================


# map_block_title
# Простая мапа для "человеческих" названий блоков.
# При желании можно потом вынести в БД.
BLOCK_TITLES: Dict[str, str] = {
    "mental_health": "Ментальное здоровье",
    "dialysis": "Диализ",
}


def map_block_title(block_code: str) -> str:
    """Вернуть человекочитаемый заголовок блока по коду."""
    if not block_code:
        return "Обучение"
    return BLOCK_TITLES.get(block_code, block_code)


# ====== API ДЛЯ ОБУЧАЮЩИХ КАРТОЧЕК (СТАРЫЙ ФРОНТ education.html) =============


# get_education_list
# Эндпоинт для фронта (education.html): список карточек по всем урокам.
@router.get("/list", response_model=List[EducationItem])
async def get_education_list(
    topic: Optional[str] = Query(
        default=None,
        description="Фильтр по теме ('stress', 'sleep', 'coping' и т.п.).",
    ),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Вернуть список обучающих карточек для фронта.

    Формат соответствует старому EducationItem:
    - id      — id карточки (LessonCard.id)
    - topic   — Блок уроков (Lesson.topic)
    - content — markdown содержимое карточки

    Если задан topic — фильтруем только по этой теме.
    """
    stmt = (
        select(LessonCard.id, Lesson.topic, LessonCard.content_md)
        .join(Lesson, LessonCard.lesson_id == Lesson.id)
        .where(Lesson.is_active.is_(True))
        .order_by(Lesson.order_index.asc(), LessonCard.order_index.asc())
    )

    if topic:
        stmt = stmt.where(Lesson.topic == topic)

    result = await session.execute(stmt)
    rows = result.all()

    items: List[EducationItem] = [
        EducationItem(
            id=row.id,
            topic=row.topic,
            content=row.content_md,
        )
        for row in rows
    ]

    return items


# get_lessons
# Список доступных уроков (на будущее для выбора модуля обучения).
@router.get("/lessons", response_model=List[LessonRead])
async def get_lessons(
    topic: Optional[str] = Query(
        default=None,
        description="Опциональный фильтр по теме ('stress', 'sleep', 'coping'...).",
    ),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Вернуть список уроков Education.

    Можно опционально отфильтровать по topic.
    """
    stmt = (
        select(Lesson)
        .where(Lesson.is_active.is_(True))
        .order_by(Lesson.order_index.asc(), Lesson.id.asc())
    )

    if topic:
        stmt = stmt.where(Lesson.topic == topic)

    result = await session.execute(stmt)
    lessons = result.scalars().all()

    return [LessonRead.model_validate(lesson) for lesson in lessons]


# get_lesson_cards
# Карточки конкретного урока по lesson_code.
@router.get("/lessons/{lesson_code}/cards", response_model=List[LessonCardRead])
async def get_lesson_cards(
    lesson_code: str,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Вернуть карточки конкретного урока по его коду (Lesson.code).

    Это пригодится, когда на фронте появится выбор урока (несколько модулей).
    """
    stmt_lesson = select(Lesson).where(
        Lesson.code == lesson_code,
        Lesson.is_active.is_(True),
    )
    result_lesson = await session.execute(stmt_lesson)
    lesson = result_lesson.scalar_one_or_none()

    if lesson is None:
        return []  # при желании можно заменить на 404

    stmt_cards = (
        select(LessonCard)
        .where(LessonCard.lesson_id == lesson.id)
        .order_by(LessonCard.order_index.asc(), LessonCard.id.asc())
    )
    result_cards = await session.execute(stmt_cards)
    cards = result_cards.scalars().all()

    return [LessonCardRead.model_validate(c) for c in cards]

# отметить урок как прочитанный (создать/обновить LessonProgress)
@router.post("/lessons/{lesson_code}/mark_read", status_code=204)
async def mark_lesson_read(
    lesson_code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Отмечает урок как прочитанный (просмотрен) по его коду (Lesson.code).

    - Ищем Lesson по Lesson.code + is_active=True.
    - Ищем LessonProgress по (lesson_id, patient_token).
    - Если нет — создаём запись, is_completed оставляем False
      (тест по-прежнему отвечает за завершение).
    """
    # 1. Находим урок
    result = await session.execute(
        select(Lesson).where(
            Lesson.code == lesson_code,
            Lesson.is_active.is_(True),
        )
    )
    lesson = result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")

    # 2. Ищем прогресс
    result = await session.execute(
        select(LessonProgress).where(
            LessonProgress.lesson_id == lesson.id,
            LessonProgress.patient_token == user.patient_token,
        )
    )
    progress = result.scalar_one_or_none()

    # 3. Если прогресса нет — создаём
    if progress is None:
        progress = LessonProgress(
            lesson_id=lesson.id,
            patient_token=user.patient_token,
            is_completed=False,
        )
        session.add(progress)

    await session.commit()



# ====== НОВЫЙ OVERVIEW ДЛЯ НАВИГАТОРА ОБУЧЕНИЯ ==============================

# get_lessons_overview
# Сводка по блокам и урокам с учётом прогресса пациента.
@router.get("/lessons/overview")
async def get_lessons_overview(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> List[Dict[str, Any]]:
    """
    Вернуть агрегированный список блоков и уроков для страницы-навигатора.

    Формат ответа:
    [
      {
        "block_code": "mental_health",
        "block_title": "Ментальное здоровье",
        "progress": {
          "lessons_total": 3,
          "lessons_read": 2,
          "tests_passed": 1
        },
        "lessons": [
          {
            "lesson_id": 1,
            "order_index": 1,
            "title": "Стресс и напряжение",
            "is_read": true,
            "is_test_passed": true
          },
          ...
        ]
      },
      ...
    ]

    Важно:
    - block_code берём из Lesson.topic (пока так, без отдельной таблицы блоков).
    - block_title строим через map_block_title().
    - is_read — есть ли LessonProgress по уроку для пациента.
    - is_test_passed — есть ли успешный LessonTestResult (passed=True) по тестам урока.
    """
    # --- 1. Берём все активные уроки ---
    stmt_lessons = (
        select(Lesson)
        .where(Lesson.is_active.is_(True))
        .order_by(Lesson.topic.asc(), Lesson.order_index.asc(), Lesson.id.asc())
    )
    result_lessons = await session.execute(stmt_lessons)
    lessons: List[Lesson] = result_lessons.scalars().all()

    if not lessons:
        return []

    lesson_ids = [l.id for l in lessons]

    # --- 2. Прогресс по урокам (LessonProgress) ---
    stmt_progress = select(LessonProgress).where(
        LessonProgress.lesson_id.in_(lesson_ids),
        LessonProgress.patient_token == user.patient_token,
    )
    result_progress = await session.execute(stmt_progress)
    progresses: List[LessonProgress] = result_progress.scalars().all()

    progress_by_lesson_id: Dict[int, LessonProgress] = {
        p.lesson_id: p for p in progresses
    }

    # --- 3. Тесты по урокам (LessonTest) ---
    stmt_tests = select(LessonTest).where(
        LessonTest.lesson_id.in_(lesson_ids),
        LessonTest.is_active.is_(True),
    )
    result_tests = await session.execute(stmt_tests)
    tests: List[LessonTest] = result_tests.scalars().all()

    test_ids = [t.id for t in tests]
    test_id_to_lesson_id: Dict[int, int] = {t.id: t.lesson_id for t in tests}

    # --- 4. Результаты тестов (LessonTestResult) для пациента ---
    lesson_has_passed_test: Dict[int, bool] = {lid: False for lid in lesson_ids}

    if test_ids:
        stmt_results = select(LessonTestResult).where(
            LessonTestResult.patient_token == user.patient_token,
            LessonTestResult.test_id.in_(test_ids),
            LessonTestResult.passed.is_(True),
        )
        result_results = await session.execute(stmt_results)
        results: List[LessonTestResult] = result_results.scalars().all()

        for r in results:
            lesson_id = test_id_to_lesson_id.get(r.test_id)
            if lesson_id is not None:
                lesson_has_passed_test[lesson_id] = True

    # --- 5. Агрегируем по блокам (topic → block_code) ---
    blocks: Dict[str, Dict[str, Any]] = {}

    for lesson in lessons:
        # используем Lesson.topic как block_code
        block_code = lesson.topic or "other"
        block_title = map_block_title(block_code)

        if block_code not in blocks:
            blocks[block_code] = {
                "block_code": block_code,
                "block_title": block_title,
                "progress": {
                    "lessons_total": 0,
                    "lessons_read": 0,
                    "tests_passed": 0,
                },
                "lessons": [],
            }

        block = blocks[block_code]

        is_read = lesson.id in progress_by_lesson_id
        is_test_passed = lesson_has_passed_test.get(lesson.id, False)

        # обновляем прогресс по блоку
        block["progress"]["lessons_total"] += 1
        if is_read:
            block["progress"]["lessons_read"] += 1
        if is_test_passed:
            block["progress"]["tests_passed"] += 1

        # добавляем урок в список
        block["lessons"].append(
            {
                "lesson_id": lesson.id,
                "lesson_code": lesson.code,
                "order_index": lesson.order_index,
                "title": getattr(lesson, "title", None) or getattr(lesson, "name", None) or lesson.code,
                "is_read": is_read,
                "is_test_passed": is_test_passed,
            }
        )

    # чтобы порядок был стабильным — отсортируем блоки и уроки внутри
    result_blocks: List[Dict[str, Any]] = []
    for block_code, block in blocks.items():
        block["lessons"].sort(key=lambda x: (x.get("order_index") or 0, x["lesson_id"]))
        result_blocks.append(block)

    # сортируем блоки по block_title (можно поменять на свой порядок)
    result_blocks.sort(key=lambda x: x["block_title"])

    return result_blocks


# ====== ТЕСТЫ К УРОКАМ =======================================================


# get_lesson_test
# Получить информацию о тесте для урока.
@router.get(
    "/lessons/{lesson_code}/test",
    response_model=TestInfo,
)
async def get_lesson_test(
    lesson_code: str,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Вернуть информацию о тесте для урока.

    Если теста ещё нет — вернётся lesson_code и test_id = null.
    """
    lesson_result = await session.execute(
        select(Lesson).where(Lesson.code == lesson_code)
    )
    lesson = lesson_result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")

    test_result = await session.execute(
        select(LessonTest)
        .where(
            LessonTest.lesson_id == lesson.id,
            LessonTest.is_active.is_(True),
        )
        .order_by(LessonTest.order_index)
        .limit(1)
    )
    test = test_result.scalar_one_or_none()

    if test is None:
        return TestInfo(
            test_id=None,
            lesson_code=lesson_code,
            title=None,
            short_description=None,
        )

    return TestInfo(
        test_id=test.id,
        lesson_code=lesson_code,
        title=test.title,
        short_description=test.short_description,
    )


# get_test_questions
# Получить список вопросов теста.
@router.get(
    "/tests/{test_id}/questions",
    response_model=TestQuestionsResponse,
)
async def get_test_questions(
    test_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Вернуть список активных вопросов для теста.
    """
    test_result = await session.execute(
        select(LessonTest).where(LessonTest.id == test_id)
    )
    test = test_result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")

    questions_result = await session.execute(
        select(LessonTestQuestion)
        .where(
            LessonTestQuestion.test_id == test_id,
            LessonTestQuestion.is_active.is_(True),
        )
        .order_by(LessonTestQuestion.order_index)
    )
    questions = questions_result.scalars().all()

    return TestQuestionsResponse(
        test_id=test_id,
        questions=[
            TestQuestion(
                id=q.id,
                order_index=q.order_index,
                question_text=q.question_text,
                options=[q.option_1, q.option_2, q.option_3, q.option_4],
            )
            for q in questions
        ],
    )


# submit_test_answers
# Отправка ответов теста и подсчёт результата.
@router.post(
    "/tests/{test_id}/submit",
    response_model=TestSubmitResponse,
)
async def submit_test_answers(
    test_id: int,
    payload: TestSubmitRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Принять ответы на тест, посчитать результат и сохранить его в LessonTestResult.

    Порог прохождения сейчас фиксированный: 60%.
    При успешной сдаче помечаем LessonProgress.is_completed = True.
    """
    test_result = await session.execute(
        select(LessonTest).where(LessonTest.id == test_id)
    )
    test = test_result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")

    questions_result = await session.execute(
        select(LessonTestQuestion).where(
            LessonTestQuestion.test_id == test_id,
            LessonTestQuestion.is_active.is_(True),
        )
    )
    questions = {q.id: q for q in questions_result.scalars().all()}

    if not questions:
        raise HTTPException(status_code=400, detail="Test has no questions")

    correct_count = 0
    total_count = len(questions)
    answers_details: list[dict] = []

    for ans in payload.answers:
        question = questions.get(ans.question_id)
        if question is None:
            # ответ на несуществующий/чужой вопрос — тихо пропускаем
            continue

        is_correct = ans.chosen_option == question.correct_option
        if is_correct:
            correct_count += 1

        answers_details.append(
            {
                "question_id": question.id,
                "chosen_option": ans.chosen_option,
                "correct_option": question.correct_option,
                "is_correct": is_correct,
            }
        )

    max_score = float(total_count)
    score = float(correct_count)

    passed = (total_count > 0) and (score / max_score >= 0.6)

    result = LessonTestResult(
        test_id=test_id,
        patient_token=user.patient_token,
        score=score,
        max_score=max_score,
        passed=passed,
        answers_json=answers_details,
    )
    session.add(result)
    await session.flush()

    if passed:
        progress_q = await session.execute(
            select(LessonProgress).where(
                LessonProgress.lesson_id == test.lesson_id,
                LessonProgress.patient_token == user.patient_token,
            )
        )
        progress = progress_q.scalar_one_or_none()

        if progress is None:
            progress = LessonProgress(
                lesson_id=test.lesson_id,
                patient_token=user.patient_token,
                is_completed=True,
            )
            session.add(progress)
        else:
            progress.is_completed = True

    await session.commit()

    return TestSubmitResponse(
        test_id=test_id,
        result_id=result.id,
        score=score,
        max_score=max_score,
        passed=passed,
    )


# get_last_test_result
# Получить последнюю попытку теста для пациента.
@router.get(
    "/tests/{test_id}/result",
    response_model=TestResultResponse,
)
async def get_last_test_result(
    test_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Вернуть последний по времени результат теста для конкретного пациента.
    """
    result_q = await session.execute(
        select(LessonTestResult)
        .where(
            LessonTestResult.test_id == test_id,
            LessonTestResult.patient_token == user.patient_token,
        )
        .order_by(LessonTestResult.created_at.desc())
        .limit(1)
    )
    result = result_q.scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Test result not found")

    return TestResultResponse(
        test_id=test_id,
        score=float(result.score),
        max_score=float(result.max_score),
        passed=result.passed,
        created_at=result.created_at,
    )
