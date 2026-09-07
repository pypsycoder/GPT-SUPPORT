# ============================================
# Dialysis Schemas: Pydantic для API
# ============================================

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Centers ---

class ShiftTimesIn(BaseModel):
    """Часы трёх диализных смен центра. Порядок строгий и без пересечений."""

    morning_start: time
    morning_end: time
    afternoon_start: time
    afternoon_end: time
    evening_start: time
    evening_end: time

    @model_validator(mode="after")
    def _strictly_ordered(self) -> "ShiftTimesIn":
        seq = [
            ("начало утренней", self.morning_start),
            ("конец утренней", self.morning_end),
            ("начало дневной", self.afternoon_start),
            ("конец дневной", self.afternoon_end),
            ("начало вечерней", self.evening_start),
            ("конец вечерней", self.evening_end),
        ]
        for (_, earlier), (label, later) in zip(seq, seq[1:]):
            if earlier >= later:
                raise ValueError(
                    "Часы смен должны идти строго по возрастанию: "
                    "утро < день < вечер, начало < конец "
                    f"(нарушено на «{label}»)"
                )
        return self


class CenterCreate(BaseModel):
    name: str
    city: str | None = None
    timezone: str = "Europe/Moscow"
    shift_times: ShiftTimesIn


class CenterUpdate(BaseModel):
    name: str | None = None
    city: str | None = None
    timezone: str | None = None
    shift_times: ShiftTimesIn | None = None


class CenterRead(BaseModel):
    id: UUID
    name: str
    city: str | None
    timezone: str
    created_at: datetime | None

    morning_start: time
    morning_end: time
    afternoon_start: time
    afternoon_end: time
    evening_start: time
    evening_end: time

    model_config = ConfigDict(from_attributes=True)


# --- Schedules ---

ShiftKind = Literal["morning", "afternoon", "evening"]


class DialysisWindow(BaseModel):
    """Окно диализа для конкретного дня: смена + часы (``HH:MM``, время центра)."""

    shift: ShiftKind
    start: str
    end: str


class DialysisScheduleBase(BaseModel):
    weekdays: list[int] = Field(..., min_length=1, max_length=7)
    shift: ShiftKind
    valid_from: date
    change_reason: str | None = None


class DialysisScheduleCreate(DialysisScheduleBase):
    pass


class DialysisScheduleRead(BaseModel):
    id: UUID
    patient_id: int
    weekdays: list[int]
    shift: str
    valid_from: date
    valid_to: date | None
    created_at: datetime | None
    created_by: int
    closed_at: datetime | None
    closed_by: int | None
    change_reason: str | None

    model_config = ConfigDict(from_attributes=True)


class ScheduleCloseAndReplaceResponse(BaseModel):
    closed: DialysisScheduleRead
    created: DialysisScheduleRead


# --- Import ---

class ImportConflictResolution(BaseModel):
    patient_id: int
    action: Literal["apply", "skip"]


class ImportConfirmRequest(BaseModel):
    preview_token: str
    apply_ready: bool = True
    resolve_conflicts: list[ImportConflictResolution] = Field(default_factory=list)


class ImportConfirmResponse(BaseModel):
    applied: int
    skipped: int
    errors: list[dict]
