from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, ConfigDict


class MeasurementContext(str, Enum):
    PRE_HD = "pre_hd"
    POST_HD = "post_hd"
    HOME = "home"
    CLINIC = "clinic"
    HOME_MORNING = "home_morning"
    HOME_EVENING = "home_evening"
    NA = "na"


class BaseVitalsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    session_id: Optional[UUID] = None
    measured_at: Optional[datetime] = None
    context: MeasurementContext = MeasurementContext.NA


class VitalsReadSchema(BaseVitalsSchema):
    id: UUID
    created_at: datetime
    updated_at: datetime


# =========================
#  АД
# =========================

class BPMeasurementBase(BaseVitalsSchema):
    systolic: int
    diastolic: int
    pulse: Optional[int] = None


class BPMeasurementCreate(BPMeasurementBase):
    pass


class BPMeasurementUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    pulse: Optional[int] = None
    session_id: Optional[UUID] = None
    measured_at: Optional[datetime] = None
    context: Optional[MeasurementContext] = None


class BPMeasurementRead(BPMeasurementBase, VitalsReadSchema):
    pass


# =========================
#  Пульс
# =========================

class PulseMeasurementBase(BaseVitalsSchema):
    bpm: int


class PulseMeasurementCreate(PulseMeasurementBase):
    pass


class PulseMeasurementUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bpm: Optional[int] = None
    session_id: Optional[UUID] = None
    measured_at: Optional[datetime] = None
    context: Optional[MeasurementContext] = None


class PulseMeasurementRead(PulseMeasurementBase, VitalsReadSchema):
    pass


# =========================
#  Вес
# =========================

class WeightMeasurementBase(BaseVitalsSchema):
    weight: float


class WeightMeasurementCreate(WeightMeasurementBase):
    pass


class WeightMeasurementUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weight: Optional[float] = None
    session_id: Optional[UUID] = None
    measured_at: Optional[datetime] = None
    context: Optional[MeasurementContext] = None


class WeightMeasurementRead(WeightMeasurementBase, VitalsReadSchema):
    pass


# =========================
#  Вода
# =========================

class WaterIntakeBase(BaseVitalsSchema):
    volume_ml: int
    liquid_type: Optional[str] = None


class WaterIntakeCreate(WaterIntakeBase):
    pass


class WaterIntakeUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    volume_ml: Optional[int] = None
    liquid_type: Optional[str] = None
    session_id: Optional[UUID] = None
    measured_at: Optional[datetime] = None
    context: Optional[MeasurementContext] = None


class WaterIntakeRead(WaterIntakeBase, VitalsReadSchema):
    pass
