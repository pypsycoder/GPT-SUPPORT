# ============================================
# Sleep Tracker Models: ORM записей сна
# ============================================
# Схема sleep в PostgreSQL. Период записи — предыдущие сутки.

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import declared_attr

from app.models import Base


class SleepRecord(Base):
    """Одна запись рутинной оценки сна (за выбранную ночь)."""

    __tablename__ = "sleep_records"

    @declared_attr
    def __table_args__(cls):  # type: ignore[override]
        return (
            Index("ix_sleep_records_patient_id", "patient_id"),
            Index("ix_sleep_records_submitted_at", "submitted_at"),
            Index("ix_sleep_records_sleep_date", "sleep_date"),
            UniqueConstraint("patient_id", "sleep_date", name="uq_sleep_records_patient_sleep_date"),
            {"schema": "sleep"},
        )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(Integer, ForeignKey("users.users.id", name="fk_sleep_records_patient_id"), nullable=False)
    sleep_date = Column(Date, nullable=False)  # дата ночи (день отхода ко сну)
    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    late_entry = Column(Boolean, nullable=False, server_default="false")
    dialysis_day = Column(Boolean, nullable=True)
    retrospective_days = Column(Integer, nullable=True)  # submitted_at.date - sleep_date
    edit_count = Column(Integer, nullable=False, server_default="0")

    sleep_onset = Column(String(5), nullable=False)   # "HH:MM"
    wake_time = Column(String(5), nullable=False)   # "HH:MM"
    tib_minutes = Column(Integer, nullable=False)
    tst_minutes = Column(Integer, nullable=False)
    sleep_efficiency_pct = Column(Float, nullable=False)

    night_awakenings = Column(String(8), nullable=False)   # none | 1-2 | 3+
    sleep_latency = Column(String(8), nullable=False)     # fast | 15-30 | 30+
    morning_wellbeing = Column(String(20), nullable=False)  # rested | slightly_tired | very_tired
    daytime_nap = Column(String(12), nullable=True)       # none | under_1h | over_1h
    sleep_disturbances = Column(ARRAY(String), nullable=True)  # ['pain','itch'] or ['none']

    @property
    def record_id(self) -> UUID:
        return self.id
