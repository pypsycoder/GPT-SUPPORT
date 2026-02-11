from __future__ import annotations

"""ORM-модели для домена d230: распорядок дня / рутина.

Содержит три основные сущности:
- BaselineRoutine: опросник-онбординг, определяющий пул активностей и два шаблона дня.
- DailyPlan: дневной план (предзаполненный по шаблону, с возможностью доработки).
- DailyVerification: вечерняя верификация выполнения плана и незапланированного поведения.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import declared_attr

from app.models import Base


class BaselineRoutine(Base):
    """Базовый шаблон рутины пациента (история версий).

    В каждый момент времени у пациента может быть только один актуальный baseline
    (valid_to IS NULL). Исторические записи сохраняются для последующего анализа.
    """

    __tablename__ = "baseline_routines"

    @declared_attr
    def __table_args__(cls):  # type: ignore[override]
        return (
            Index("ix_baseline_routines_patient_id", "patient_id"),
            # Один активный baseline на пациента
            Index(
                "one_active_baseline_per_patient",
                "patient_id",
                unique=True,
                postgresql_where=text("valid_to IS NULL"),
            ),
            {"schema": "routine"},
        )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(
        Integer,
        ForeignKey("users.users.id", ondelete="CASCADE"),
        nullable=False,
    )

    completed_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    # Пул категорий активностей пациента (ActivityCategory[])
    activity_pool = Column(ARRAY(String(length=32)), nullable=False)

    # Шаблон диализного и недиализного дня: массивы категорий
    dialysis_day_template = Column(ARRAY(String(length=32)), nullable=False)
    non_dialysis_day_template = Column(ARRAY(String(length=32)), nullable=False)

    # Время планирования дня (morning | evening)
    planning_time = Column(String(length=16), nullable=False)

    # Версионирование baseline во времени
    valid_from = Column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    valid_to = Column(Date, nullable=True)


class DailyPlan(Base):
    """Дневной план пациента (планер).

    Ограничение уникальности: один план на (patient_id, plan_date).
    """

    __tablename__ = "daily_plans"

    @declared_attr
    def __table_args__(cls):  # type: ignore[override]
        return (
            UniqueConstraint(
                "patient_id",
                "plan_date",
                name="uq_daily_plans_patient_plan_date",
            ),
            Index("ix_daily_plans_patient_id", "patient_id"),
            Index("ix_daily_plans_plan_date", "plan_date"),
            {"schema": "routine"},
        )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(
        Integer,
        ForeignKey("users.users.id", ondelete="CASCADE"),
        nullable=False,
    )

    plan_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    dialysis_day = Column(Boolean, nullable=True)

    # JSON-структуры: category -> { planned: bool, planned_duration: str | null }
    template_activities = Column(JSONB, nullable=True)
    added_from_pool = Column(JSONB, nullable=True)
    # Кастомные активности: список объектов {text, planned_duration}
    custom_activities = Column(JSONB, nullable=True)

    edit_count = Column(Integer, nullable=False, server_default=text("0"))
    retrospective_days = Column(Integer, nullable=True)


class DailyVerification(Base):
    """Вечерняя верификация выполнения плана и незапланированных активностей."""

    __tablename__ = "daily_verifications"

    @declared_attr
    def __table_args__(cls):  # type: ignore[override]
        return (
            UniqueConstraint(
                "patient_id",
                "verification_date",
                name="uq_daily_verifications_patient_date",
            ),
            Index("ix_daily_verifications_patient_id", "patient_id"),
            Index("ix_daily_verifications_date", "verification_date"),
            {"schema": "routine"},
        )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    plan_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("routine.daily_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    patient_id = Column(
        Integer,
        ForeignKey("users.users.id", ondelete="CASCADE"),
        nullable=False,
    )

    verification_date = Column(Date, nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    dialysis_day = Column(Boolean, nullable=True)

    # JSON-структуры исполнения: category -> { done: str, actual_duration: str | null }
    template_executed = Column(JSONB, nullable=True)
    pool_added_executed = Column(JSONB, nullable=True)
    # Кастомные запланированные: text -> { done, actual_duration }
    custom_executed = Column(JSONB, nullable=True)

    # Незапланированные активности: список категорий и одна произвольная строка
    unplanned_executed = Column(ARRAY(String(length=32)), nullable=True)
    custom_unplanned = Column(String(length=255), nullable=True)

    day_control_score = Column(Integer, nullable=False)

    edit_count = Column(Integer, nullable=False, server_default=text("0"))
    retrospective_days = Column(Integer, nullable=True)


def compute_retrospective_days(submitted_at: datetime, target_date: date) -> int | None:
    """Хелпер для вычисления retrospective_days (целое количество дней между датами)."""
    if submitted_at is None or target_date is None:
        return None
    return (submitted_at.date() - target_date).days


