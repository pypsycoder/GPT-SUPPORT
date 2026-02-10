# ============================================
# Dialysis Models: Центры и расписания диализа
# ============================================

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    ARRAY,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models import Base

# PostgreSQL ENUM для смены (создаётся в миграции)
SHIFT_ENUM = Enum(
    "morning",
    "afternoon",
    "evening",
    name="shift_enum",
    create_constraint=True,
)


class Center(Base):
    """Диализный центр."""

    __tablename__ = "centers"
    # public schema by default

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    city = Column(String, nullable=True)
    timezone = Column(String, nullable=False, default="Europe/Moscow")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DialysisSchedule(Base):
    """Расписание диализа пациента (история не удаляется)."""

    __tablename__ = "dialysis_schedules"
    __table_args__ = (
        Index(
            "one_active_schedule_per_patient",
            "patient_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    # weekdays: ISO 1=Пн .. 7=Вс
    weekdays = Column(ARRAY(Integer), nullable=False)
    shift = Column(SHIFT_ENUM, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)  # NULL = текущее активное расписание

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.researchers.id"), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.researchers.id"), nullable=True)
    change_reason = Column(String, nullable=True)
