from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BaseVitalsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    session_id: Optional[UUID] = None
    measured_at: Optional[datetime] = None


class VitalsReadSchema(BaseVitalsSchema):
    id: UUID
    created_at: datetime
    updated_at: datetime


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


class BPMeasurementRead(BPMeasurementBase, VitalsReadSchema):
    pass


class PulseMeasurementBase(BaseVitalsSchema):
    bpm: int


class PulseMeasurementCreate(PulseMeasurementBase):
    pass


class PulseMeasurementUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bpm: Optional[int] = None
    session_id: Optional[UUID] = None
    measured_at: Optional[datetime] = None


class PulseMeasurementRead(PulseMeasurementBase, VitalsReadSchema):
    pass


class WeightMeasurementBase(BaseVitalsSchema):
    weight: float


class WeightMeasurementCreate(WeightMeasurementBase):
    pass


class WeightMeasurementUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weight: Optional[float] = None
    session_id: Optional[UUID] = None
    measured_at: Optional[datetime] = None


class WeightMeasurementRead(WeightMeasurementBase, VitalsReadSchema):
    pass


