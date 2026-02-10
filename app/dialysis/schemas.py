# ============================================
# Dialysis Schemas: Pydantic для API
# ============================================

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# --- Centers ---

class CenterCreate(BaseModel):
    name: str
    city: str | None = None
    timezone: str = "Europe/Moscow"


class CenterRead(BaseModel):
    id: UUID
    name: str
    city: str | None
    timezone: str
    created_at: datetime | None

    class Config:
        from_attributes = True


# --- Schedules ---

ShiftKind = Literal["morning", "afternoon", "evening"]


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

    class Config:
        from_attributes = True


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
