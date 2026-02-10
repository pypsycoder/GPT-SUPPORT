# ============================================
# Vitals Models: ORM-модели витальных показателей
# ============================================
# BPMeasurement, PulseMeasurement, WeightMeasurement, WaterIntake.
# Схема vitals в PostgreSQL.

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declared_attr

from app.models import Base


class VitalsBase(Base):
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=True)
    measured_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @declared_attr
    def __table_args__(cls):  # type: ignore[override]
        return (
            Index(f"ix_{cls.__tablename__}_session_id", "session_id"),
            Index(f"ix_{cls.__tablename__}_measured_at", "measured_at"),
            {"schema": "vitals"},
        )


class BPMeasurement(VitalsBase):
    __tablename__ = "bp_measurements"

    systolic = Column(Integer, nullable=False)
    diastolic = Column(Integer, nullable=False)
    pulse = Column(Integer, nullable=True)
    # контекст измерения давления (до/после диализа, дома и т.д.)
    context = Column(String(length=32), nullable=False, server_default="na")


class PulseMeasurement(VitalsBase):
    __tablename__ = "pulse_measurements"

    bpm = Column(Integer, nullable=False)
    # контекст измерения пульса
    context = Column(String(length=32), nullable=False, server_default="na")


class WeightMeasurement(VitalsBase):
    __tablename__ = "weight_measurements"

    weight = Column(Numeric(6, 2), nullable=False)
    # контекст измерения веса (до/после, дома утром/вечером)
    context = Column(String(length=32), nullable=False, server_default="na")


class WaterIntake(VitalsBase):
    __tablename__ = "water_intake"

    volume_ml = Column(Integer, nullable=False)
    # тип жидкости (опционально для будущего расширения)
    liquid_type = Column(String(length=32), nullable=True)
    # контекст (утро/день/вечер, с едой/без еды)
    context = Column(String(length=32), nullable=False, server_default="na")
