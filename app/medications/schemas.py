# ============================================
# Medications: Pydantic schemas for Prescriptions & Intakes API
# ============================================

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --- Prescriptions ---


class PrescriptionCreate(BaseModel):
    medication_name: str = Field(..., min_length=1, max_length=200)
    dose: float
    dose_unit: str = Field(..., min_length=1, max_length=20)
    frequency_times_per_day: int
    intake_schedule: list[str]
    route: str = Field(..., min_length=1, max_length=50)
    start_date: date
    end_date: Optional[date] = None
    indication: Optional[str] = Field(None, max_length=500)
    instructions: Optional[str] = Field(None, max_length=500)
    status: str = "active"
    prescribed_by: Optional[int] = None

    @field_validator("dose")
    @classmethod
    def dose_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Доза должна быть больше 0")
        return v

    @field_validator("frequency_times_per_day")
    @classmethod
    def freq_range(cls, v: int) -> int:
        if not 1 <= v <= 6:
            raise ValueError("Частота приёма: от 1 до 6 раз в день")
        return v

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date | None, info) -> date | None:
        if v and "start_date" in info.data and info.data["start_date"] and v < info.data["start_date"]:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        return v

    @model_validator(mode="after")
    def schedule_valid(self) -> PrescriptionCreate:
        allowed = {"morning", "afternoon", "evening"}
        freq = self.frequency_times_per_day
        schedule = self.intake_schedule
        if len(schedule) != freq:
            raise ValueError(
                f"Количество слотов ({len(schedule)}) должно совпадать с частотой приёма ({freq})"
            )
        for slot in schedule:
            if slot not in allowed:
                raise ValueError(f"Недопустимый слот: {slot}. Допустимые: morning, afternoon, evening")
        return self


class PrescriptionUpdate(PrescriptionCreate):
    """Полная замена полей назначения (PUT)."""
    pass


class PrescriptionResponse(BaseModel):
    id: int
    patient_id: int
    medication_name: str
    dose: float
    dose_unit: str
    frequency_times_per_day: int
    intake_schedule: list[str]
    route: str
    start_date: date
    end_date: Optional[date]
    indication: Optional[str]
    instructions: Optional[str]
    status: str
    prescribed_by: Optional[int]
    adherence_rate: float
    today_taken_slots: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Intakes ---


class IntakeCreate(BaseModel):
    prescription_id: int
    intake_datetime: datetime
    actual_dose: float
    intake_slot: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("actual_dose")
    @classmethod
    def dose_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Доза должна быть больше 0")
        return v


class IntakeUpdate(BaseModel):
    intake_datetime: Optional[datetime] = None
    actual_dose: Optional[float] = None
    intake_slot: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("actual_dose")
    @classmethod
    def dose_positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("Доза должна быть больше 0")
        return v


class IntakeResponse(BaseModel):
    id: int
    prescription_id: int
    patient_id: int
    intake_datetime: datetime
    actual_dose: float
    intake_slot: Optional[str]
    notes: Optional[str]
    is_retrospective: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
