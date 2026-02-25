## Pydantic-схемы для работы с обучающими материалами (education).

# app/education/schemas.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


# EducationItem – минимальная схема обучающего материала
class EducationItem(BaseModel):
    """
    Обучающий материал для пациента.

    Минимальный набор полей для MVP:
    - id: внутренний идентификатор карточки
    - topic: тема/блок (например, "stress", "sleep")
    - content: содержимое (Markdown/текст)
    """
    id: int
    topic: str
    content: str

    # При желании потом добавим:
    # title: Optional[str]
    # short: Optional[str]
    # order: Optional[int]

# схема урока (Lesson)
class LessonRead(BaseModel):
    id: int
    code: str
    topic: str
    title: str
    short_description: Optional[str] = None
    order_index: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# схема карточки урока (LessonCard) – для новых эндпоинтов, если пригодится
class LessonCardRead(BaseModel):
    id: int
    lesson_id: int
    order_index: int
    card_type: str
    content_md: str

    class Config:
        from_attributes = True


# ---------------------------
# Pydantic-схемы для тестов
# ---------------------------

class TestInfo(BaseModel):
    test_id: int | None
    lesson_code: str
    title: str | None = None
    short_description: str | None = None


class TestQuestion(BaseModel):
    id: int
    order_index: int
    question_text: str
    options: List[str]


class TestQuestionsResponse(BaseModel):
    test_id: int
    questions: List[TestQuestion]


class TestAnswer(BaseModel):
    question_id: int
    chosen_option: int  # 1..4


class TestSubmitRequest(BaseModel):
    answers: List[TestAnswer]


class TestSubmitResponse(BaseModel):
    test_id: int
    result_id: int
    score: float
    max_score: float
    passed: bool
    practice_done: bool = False
    practice_completed_at: Optional[datetime] = None


class TestResultResponse(BaseModel):
    test_id: int
    score: float
    max_score: float
    passed: bool
    created_at: datetime
