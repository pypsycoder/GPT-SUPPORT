from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.sql import func

from app.models import Base


# Измерения артериального давления и пульса
class BpMeasurement(Base):
    __tablename__ = "bp_measurement"
    __table_args__ = {"schema": "vitals"}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    systolic_mm_hg = Column(Integer, nullable=False)
    diastolic_mm_hg = Column(Integer, nullable=False)
    pulse_bpm = Column(Integer)
    measured_at = Column(DateTime, nullable=False, server_default=func.now())
    context = Column(String)


# События приёма жидкости
class FluidIntakeEvent(Base):
    __tablename__ = "fluid_intake_event"
    __table_args__ = {"schema": "vitals"}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    volume_ml = Column(Integer, nullable=False)
    intake_type = Column(String)
    recorded_at = Column(DateTime, nullable=False, server_default=func.now())


# Измерения массы тела
class WeightMeasurement(Base):
    __tablename__ = "weight_measurement"
    __table_args__ = {"schema": "vitals"}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    weight_kg = Column(Numeric(5, 2), nullable=False)
    measured_at = Column(DateTime, nullable=False, server_default=func.now())
    context = Column(String)
