from __future__ import annotations

"""Pydantic-схемы и enum-ы для модуля d230 (рутина / распорядок дня)."""

from datetime import date, datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator


# --- Базовые enum-ы домена ---


ActivityCategory = Literal[
    "physical",
    "household",
    "work",
    "leisure",
    "social",
    "self_care",
    "diet",
]

DurationCode = Literal["15min", "30min", "1h", "1h_plus"]

DietExecution = Literal["fully", "partly", "no"]


PLANNING_TIME_VALUES = ("morning", "evening")


class ActivityPlan(BaseModel):
    """Состояние одной активности в плане."""

    planned: bool = False
    planned_duration: Optional[DurationCode] = None


class ActivityExecution(BaseModel):
    """Исполнение одной активности при верификации."""

    done: Optional[Literal["yes", "no", "partly"]] = None
    actual_duration: Optional[DurationCode] = None


# --- Baseline (онбординг) ---


class BaselineRoutineCreate(BaseModel):
    """Создание/обновление baseline-опросника (шаги 1–4)."""

    activity_pool: List[ActivityCategory] = Field(..., description="Пул активностей пациента")
    dialysis_day_template: List[ActivityCategory] = Field(..., description="Шаблон диализного дня")
    non_dialysis_day_template: List[ActivityCategory] = Field(..., description="Шаблон недиализного дня")
    planning_time: str = Field(..., description="Время планирования: morning | evening")

    @field_validator("planning_time")
    @classmethod
    def validate_planning_time(cls, v: str) -> str:
        if v not in PLANNING_TIME_VALUES:
            raise ValueError("Допустимые значения: morning, evening")
        return v


class BaselineRoutineRead(BaseModel):
    """Актуальный baseline пациента."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: int
    completed_at: datetime
    activity_pool: List[ActivityCategory]
    dialysis_day_template: List[ActivityCategory]
    non_dialysis_day_template: List[ActivityCategory]
    planning_time: str
    valid_from: date
    valid_to: Optional[date]


# --- Планер ---


class DailyPlanTemplateActivities(RootModel[Dict[ActivityCategory, ActivityPlan]]):
    """Маппинг категорий из шаблона на состояние в плане."""


class DailyPlanPoolActivities(RootModel[Dict[ActivityCategory, ActivityPlan]]):
    """Маппинг категорий из пула, добавленных сверх шаблона."""


class CustomPlannedActivity(BaseModel):
    text: str
    planned_duration: Optional[DurationCode] = None


class DailyPlanBase(BaseModel):
    plan_date: date
    dialysis_day: Optional[bool] = None
    template_activities: Optional[Dict[ActivityCategory, ActivityPlan]] = None
    added_from_pool: Optional[Dict[ActivityCategory, ActivityPlan]] = None
    custom_activities: Optional[List[Optional[CustomPlannedActivity]]] = None


class DailyPlanCreate(DailyPlanBase):
    """Создание/перезапись плана.

    patient_id берётся из контекста авторизации.
    """


class DailyPlanRead(BaseModel):
    """Ответ API: дневной план пациента (id=None для черновика без сохранения)."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None
    patient_id: int
    plan_date: date
    created_at: datetime
    dialysis_day: Optional[bool]
    template_activities: Optional[Dict[ActivityCategory, ActivityPlan]]
    added_from_pool: Optional[Dict[ActivityCategory, ActivityPlan]]
    custom_activities: Optional[List[Optional[CustomPlannedActivity]]]
    edit_count: int
    retrospective_days: Optional[int]


# --- Верификация ---


class DailyVerificationBase(BaseModel):
    verification_date: date
    dialysis_day: Optional[bool] = None

    template_executed: Optional[Dict[ActivityCategory, ActivityExecution]] = None
    pool_added_executed: Optional[Dict[ActivityCategory, ActivityExecution]] = None
    custom_executed: Optional[Dict[str, ActivityExecution]] = None

    unplanned_executed: Optional[List[ActivityCategory]] = None
    custom_unplanned: Optional[str] = None

    day_control_score: int

    @field_validator("day_control_score")
    @classmethod
    def validate_day_control_score(cls, v: int) -> int:
        if not (0 <= v <= 10):
            raise ValueError("day_control_score должен быть в диапазоне 0–10")
        return v


class DailyVerificationCreate(DailyVerificationBase):
    """Создание/обновление верификации за день."""


class DailyVerificationRead(BaseModel):
    """Ответ API: верификация за день."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: Optional[UUID]
    patient_id: int
    verification_date: date
    submitted_at: datetime
    dialysis_day: Optional[bool]
    template_executed: Optional[Dict[ActivityCategory, ActivityExecution]]
    pool_added_executed: Optional[Dict[ActivityCategory, ActivityExecution]]
    custom_executed: Optional[Dict[str, ActivityExecution]]
    unplanned_executed: Optional[List[ActivityCategory]]
    custom_unplanned: Optional[str]
    day_control_score: int
    edit_count: int
    retrospective_days: Optional[int]


# --- Метрики / отчётность ---


class DailyRoutineMetrics(BaseModel):
    """Дневные метрики по модулю d230."""

    plan_date: date
    dialysis_day: Optional[bool]
    planning_time: Optional[str]

    baseline_execution_rate: Optional[float] = None
    initiative_rate: Optional[float] = None
    day_control_score: Optional[int] = None
    unplanned_count: Optional[int] = None
    time_allocation_accuracy: Optional[float] = None


