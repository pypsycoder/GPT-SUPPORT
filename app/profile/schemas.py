# app/profile/schemas.py
"""Pydantic-схемы для профиля пациента."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProfileUpdate(BaseModel):
    """Данные для обновления профиля пациента."""

    full_name: Optional[str] = Field(None, max_length=255)
    age: Optional[int] = Field(None, ge=0, le=150)
    gender: Optional[str] = Field(None, pattern=r"^(male|female)$")


class LastBP(BaseModel):
    """Последнее измерение артериального давления."""

    systolic: int
    diastolic: int
    pulse: Optional[int] = None
    measured_at: datetime


class LastPulse(BaseModel):
    """Последнее измерение пульса."""

    bpm: int
    measured_at: datetime


class LastWeight(BaseModel):
    """Последнее измерение веса."""

    weight: float
    measured_at: datetime


class VitalsSummary(BaseModel):
    """Сводка по витальным показателям."""

    last_bp: Optional[LastBP] = None
    last_pulse: Optional[LastPulse] = None
    last_weight: Optional[LastWeight] = None
    last_water_today_ml: Optional[int] = None


class EducationSummary(BaseModel):
    """Сводка по обучению."""

    lessons_total: int = 0
    lessons_completed: int = 0
    tests_passed: int = 0
    practices_done: int = 0
    last_activity_at: Optional[datetime] = None


class LastScale(BaseModel):
    """Последняя пройденная шкала."""

    code: str
    name: str
    measured_at: datetime


class ScalesSummary(BaseModel):
    """Сводка по психологическим шкалам."""

    scales_passed: int = 0
    scales_available: int = 0
    last_scale: Optional[LastScale] = None


class ProfileSummary(BaseModel):
    """Полная сводка профиля пациента."""

    # Базовые данные пользователя
    id: int
    full_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    telegram_id: Optional[str] = None
    consent_personal_data: bool
    consent_bot_use: bool

    # Сводки активности
    vitals: VitalsSummary
    education: EducationSummary
    scales: ScalesSummary

    model_config = ConfigDict(from_attributes=True)
