# app/education/models.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Numeric,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.users.models import User


EDUCATION_SCHEMA = "education"


# модель урока
class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = {"schema": EDUCATION_SCHEMA}

    # PK
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # машинный код урока, например 'stress_intro_1'
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    # тема урока: 'stress', 'sleep', 'coping' и т.п.
    topic: Mapped[str] = mapped_column(String(50), index=True)

    # видимый заголовок
    title: Mapped[str] = mapped_column(String(255))

    # краткое описание (для списков)
    short_description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    # порядок отображения модулей
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    # активен ли урок
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # служебные поля
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # связи
    cards: Mapped[List["LessonCard"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
    )
    practices: Mapped[List["Practice"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
    )
    tests: Mapped[List["LessonTest"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
    )


# модель карточки урока
class LessonCard(Base):
    __tablename__ = "lesson_cards"
    __table_args__ = {"schema": EDUCATION_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # внешний ключ на урок
    lesson_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{EDUCATION_SCHEMA}.lessons.id", ondelete="CASCADE"),
        index=True,
    )

    # порядок карточки в уроке
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    # тип карточки (на будущее: 'text', 'info', 'warning')
    card_type: Mapped[str] = mapped_column(String(30), default="text")

    # markdown-текст карточки
    content_md: Mapped[str] = mapped_column(Text)

    # связь
    lesson: Mapped["Lesson"] = relationship(back_populates="cards")



# модель практики (упражнения) по уроку
class Practice(Base):
    __tablename__ = "practices"
    __table_args__ = {"schema": EDUCATION_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    lesson_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{EDUCATION_SCHEMA}.lessons.id", ondelete="CASCADE"),
        index=True,
    )

    # заголовок практики (например, "Дыхательное упражнение 4-6-8")
    title: Mapped[str] = mapped_column(String(255))

    # текст инструкции в markdown
    description_md: Mapped[str] = mapped_column(Text)

    # порядок практики в уроке
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # связи
    lesson: Mapped["Lesson"] = relationship(back_populates="practices")
    logs: Mapped[List["PracticeLog"]] = relationship(
        back_populates="practice",
        cascade="all, delete-orphan",
    )


# модель лога практики (выполнение упражнения)
class PracticeLog(Base):
    __tablename__ = "practice_logs"
    __table_args__ = {"schema": EDUCATION_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.users.id", ondelete="CASCADE"),
        index=True,
    )

    practice_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{EDUCATION_SCHEMA}.practices.id", ondelete="CASCADE"),
        index=True,
    )

    # когда выполнял практику
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    # получилось / не получилось
    success: Mapped[bool] = mapped_column(Boolean, default=True)

    # субъективный эффект 0–10 (может быть пустым)
    effect_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # комментарий от пациента (опционально)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # связи
    user: Mapped["User"] = relationship()
    practice: Mapped["Practice"] = relationship(back_populates="logs")

# ---------------------------
# Прогресс урока (для Web, через patient_token)
# ---------------------------

class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = {"schema": EDUCATION_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    patient_token: Mapped[str] = mapped_column(String(64), index=True)

    lesson_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{EDUCATION_SCHEMA}.lessons.id", ondelete="CASCADE"),
        index=True,
    )

    # номер последней просмотренной карточки (1...N). 0 — не начинал
    last_card_index: Mapped[int] = mapped_column(Integer, default=0)

    # завершен ли урок (все карточки + тест пройден)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ---------------------------
# Тест к уроку
# ---------------------------

class LessonTest(Base):
    __tablename__ = "lesson_tests"
    __table_args__ = {"schema": EDUCATION_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    lesson_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{EDUCATION_SCHEMA}.lessons.id", ondelete="CASCADE"),
        index=True,
    )

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    short_description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # связи
    lesson: Mapped["Lesson"] = relationship(back_populates="tests")
    questions: Mapped[List["LessonTestQuestion"]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
    )
    results: Mapped[List["LessonTestResult"]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
    )


# ---------------------------
# Вопрос теста
# ---------------------------

class LessonTestQuestion(Base):
    __tablename__ = "lesson_test_questions"
    __table_args__ = {"schema": EDUCATION_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    test_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{EDUCATION_SCHEMA}.lesson_tests.id", ondelete="CASCADE"),
        index=True,
    )

    order_index: Mapped[int] = mapped_column(Integer)

    question_text: Mapped[str] = mapped_column(Text)

    option_1: Mapped[str] = mapped_column(Text)
    option_2: Mapped[str] = mapped_column(Text)
    option_3: Mapped[str] = mapped_column(Text)
    option_4: Mapped[str] = mapped_column(Text)

    correct_option: Mapped[int] = mapped_column(Integer)  # 1..4
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # связь
    test: Mapped["LessonTest"] = relationship(back_populates="questions")


# ---------------------------
# Результат прохождения теста (для Web, через patient_token)
# ---------------------------

class LessonTestResult(Base):
    __tablename__ = "lesson_test_results"
    __table_args__ = {"schema": EDUCATION_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # на какой тест (LessonTest)
    test_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{EDUCATION_SCHEMA}.lesson_tests.id", ondelete="CASCADE"),
        index=True,
    )

    patient_token: Mapped[str] = mapped_column(String(64), index=True)

    score: Mapped[float] = mapped_column(Numeric, default=0)
    max_score: Mapped[float] = mapped_column(Numeric, default=0)

    passed: Mapped[bool] = mapped_column(Boolean, default=False)

    # массив: [{question_id, chosen_option, is_correct}, ...]
    answers_json: Mapped[dict] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    # связь
    test: Mapped["LessonTest"] = relationship(back_populates="results")
