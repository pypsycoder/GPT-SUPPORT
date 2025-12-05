# app/education/router.py

from __future__ import annotations

from typing import List, Optional

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
router = APIRouter(tags=["education"],)


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
    - topic   — тема урока (Lesson.topic)
    - content — markdown содержимое карточки

    Если задан topic — фильтруем только по этой теме.
    """
    # базовый запрос: берём карточку + урок
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

    # конвертация в pydantic-схему EducationItem
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
    Вернуть карточки конкретного урока по его коду (lesson.code).

    Это пригодится, когда на фронте появится выбор урока (несколько модулей).
    """
    # находим урок по коду
    stmt_lesson = select(Lesson).where(Lesson.code == lesson_code, Lesson.is_active.is_(True))
    result_lesson = await session.execute(stmt_lesson)
    lesson = result_lesson.scalar_one_or_none()

    if lesson is None:
        return []  # можно заменить на 404, если захочешь

    # тянем карточки этого урока
    stmt_cards = (
        select(LessonCard)
        .where(LessonCard.lesson_id == lesson.id)
        .order_by(LessonCard.order_index.asc(), LessonCard.id.asc())
    )
    result_cards = await session.execute(stmt_cards)
    cards = result_cards.scalars().all()

    return [LessonCardRead.model_validate(c) for c in cards]

# получить информацию о тесте для урока
@router.get(
    "/lessons/{lesson_code}/test",
    response_model=TestInfo,
)
async def get_lesson_test(
    lesson_code: str,
    session: AsyncSession = Depends(get_async_session),
):
    # ищем урок
    lesson_result = await session.execute(
        select(Lesson).where(Lesson.code == lesson_code)
    )
    lesson = lesson_result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")

    # ищем активный тест для урока
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
        # теста ещё нет — возвращаем lesson_code, но test_id = null
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


# получить список вопросов теста
@router.get(
    "/tests/{test_id}/questions",
    response_model=TestQuestionsResponse,
)
async def get_test_questions(
    test_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    # проверим, что тест существует
    test_result = await session.execute(
        select(LessonTest).where(LessonTest.id == test_id)
    )
    test = test_result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")

    # достаём вопросы
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

# отправка ответов теста и подсчёт результата
@router.post(
    "/tests/{test_id}/submit",
    response_model=TestSubmitResponse,
)
async def submit_test_answers(
    test_id: int,
    payload: TestSubmitRequest,
    session: AsyncSession = Depends(get_async_session),
):
    # проверяем, что тест существует
    test_result = await session.execute(
        select(LessonTest).where(LessonTest.id == test_id)
    )
    test = test_result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")

    # забираем только активные вопросы этого теста
    questions_result = await session.execute(
        select(LessonTestQuestion).where(
            LessonTestQuestion.test_id == test_id,
            LessonTestQuestion.is_active.is_(True),
        )
    )
    questions = {q.id: q for q in questions_result.scalars().all()}

    if not questions:
        raise HTTPException(status_code=400, detail="Test has no questions")

    # считаем баллы
    correct_count = 0
    total_count = len(questions)
    answers_details: list[dict] = []

    for ans in payload.answers:
        question = questions.get(ans.question_id)
        if question is None:
            # если вдруг прилетел ответ на чужой/несуществующий вопрос — пропускаем
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

    # простое правило: порог 60%
    passed = (total_count > 0) and (score / max_score >= 0.6)

    # сохраняем результат теста
    result = LessonTestResult(
        test_id=test_id,
        patient_token=payload.patient_token,
        score=score,
        max_score=max_score,
        passed=passed,
        answers_json=answers_details,
    )
    session.add(result)
    await session.flush()  # получаем result.id без отдельного запроса

    # --- обновление LessonProgress при успешной сдаче теста ---
    if passed:
        # пробуем найти существующий прогресс по этому уроку и пациенту
        progress_q = await session.execute(
            select(LessonProgress).where(
                LessonProgress.lesson_id == test.lesson_id,
                LessonProgress.patient_token == payload.patient_token,
            )
        )
        progress = progress_q.scalar_one_or_none()

        if progress is None:
            # создаём новую запись прогресса
            progress = LessonProgress(
                lesson_id=test.lesson_id,
                patient_token=payload.patient_token,
                # last_card_index можно оставить None или 0,
                # если не хочешь сейчас городить логику по карточкам
                is_completed=True,
            )
            session.add(progress)
        else:
            # отмечаем урок завершённым
            progress.is_completed = True
        # updated_at, если он `server_default`/`onupdate`, обновится сам

    await session.commit()

    return TestSubmitResponse(
        test_id=test_id,
        result_id=result.id,
        score=score,
        max_score=max_score,
        passed=passed,
    )


# получить последнюю попытку теста для пациента
@router.get(
    "/tests/{test_id}/result",
    response_model=TestResultResponse,
)
async def get_last_test_result(
    test_id: int,
    patient_token: str,
    session: AsyncSession = Depends(get_async_session),
):
    result_q = await session.execute(
        select(LessonTestResult)
        .where(
            LessonTestResult.test_id == test_id,
            LessonTestResult.patient_token == patient_token,
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
