# ============================================
# Medications: Pydantic schemas for API
# ============================================

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.medications.models import (
    FoodRelation,
    FrequencyType,
    IntakeStatus,
    MedicationCategory,
)


# --- Reference (справочник) ---


class MedicationReferenceOut(BaseModel):
    """Препарат из справочника для автокомплита."""

    id: UUID
    name_ru: str
    name_trade: str | None
    category: MedicationCategory
    typical_doses: list[str]
    food_relation_hint: FoodRelation | None

    model_config = ConfigDict(from_attributes=True)


class MedicationReferenceListOut(BaseModel):
    """Список препаратов справочника."""

    items: list[MedicationReferenceOut]
    total: int


# --- Medication (препараты пациента) ---


class MedicationCreate(BaseModel):
    """Создание препарата."""

    reference_id: UUID | None = None
    custom_name: str | None = None
    dose: str = Field(..., min_length=1, max_length=100)
    frequency_type: FrequencyType
    days_of_week: list[int] | None = None  # 0-6
    times_of_day: list[time] = Field(..., min_length=1)
    relation_to_food: FoodRelation | None = None
    notes: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def validate_name_source(self) -> MedicationCreate:
        if self.reference_id is None and not self.custom_name:
            raise ValueError("Укажите препарат из справочника или введите название")
        return self

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, v: list[int] | None) -> list[int] | None:
        if v is not None:
            if not all(0 <= d <= 6 for d in v):
                raise ValueError("Дни недели должны быть от 0 (пн) до 6 (вс)")
            if len(v) == 0:
                raise ValueError("Выберите хотя бы один день")
        return v


class MedicationUpdate(BaseModel):
    """Обновление препарата."""

    dose: str | None = Field(None, min_length=1, max_length=100)
    frequency_type: FrequencyType | None = None
    days_of_week: list[int] | None = None
    times_of_day: list[time] | None = None
    relation_to_food: FoodRelation | None = None
    notes: str | None = Field(None, max_length=1000)
    change_reason: str | None = Field(None, max_length=500)

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and not all(0 <= d <= 6 for d in v):
            raise ValueError("Дни недели должны быть от 0 (пн) до 6 (вс)")
        return v


class MedicationOut(BaseModel):
    """Препарат пациента (полный)."""

    id: UUID
    display_name: str
    dose: str
    frequency_type: FrequencyType
    days_of_week: list[int] | None
    times_of_day: list[time]
    relation_to_food: FoodRelation | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    reference: MedicationReferenceOut | None = None

    model_config = ConfigDict(from_attributes=True)


class MedicationListOut(BaseModel):
    """Список препаратов пациента."""

    items: list[MedicationOut]
    total: int


# --- History ---


class MedicationHistoryOut(BaseModel):
    """Запись истории изменений."""

    id: UUID
    dose: str
    frequency_type: FrequencyType
    days_of_week: list[int] | None
    times_of_day: list[time]
    relation_to_food: FoodRelation | None
    notes: str | None
    changed_at: datetime
    change_reason: str | None

    model_config = ConfigDict(from_attributes=True)


# --- Schedule ---


class ScheduleSlot(BaseModel):
    """Один слот в расписании (один приём)."""

    medication_id: UUID
    medication_name: str
    dose: str
    scheduled_time: time
    relation_to_food: FoodRelation | None
    notes: str | None
    intake_status: IntakeStatus | None = None  # None = не отмечено
    taken_at: datetime | None = None


class ScheduleTimeGroup(BaseModel):
    """Группа приёмов на одно время."""

    time: time
    slots: list[ScheduleSlot]


class DayScheduleOut(BaseModel):
    """Расписание на день."""

    date: date
    day_of_week: int  # 0-6
    day_name: str  # "понедельник"
    groups: list[ScheduleTimeGroup]
    tracking_enabled: bool


# --- Intake ---


class IntakeRecordCreate(BaseModel):
    """Отметка о приёме/пропуске."""

    medication_id: UUID
    scheduled_date: date
    scheduled_time: time
    status: IntakeStatus
    taken_at: datetime | None = None  # Для status=taken, по умолчанию now()


class IntakeRecordOut(BaseModel):
    """Запись о приёме."""

    id: UUID
    medication_id: UUID
    medication_name: str
    scheduled_date: date
    scheduled_time: time
    status: IntakeStatus
    taken_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Settings ---


class MedicationSettingsOut(BaseModel):
    """Настройки модуля."""

    tracking_enabled: bool


class MedicationSettingsUpdate(BaseModel):
    """Обновление настроек."""

    tracking_enabled: bool
