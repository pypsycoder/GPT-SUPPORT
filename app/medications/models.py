# ============================================
# Medications module: ORM models
# Таблицы: medication_prescriptions, medication_intakes
# Schema: "medications"
# ============================================

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from app.models import Base

MEDICATIONS_SCHEMA = "medications"


class MedicationPrescription(Base):
    """Назначение препарата (врачебное или самоназначение пациента)."""

    __tablename__ = "medication_prescriptions"
    __table_args__ = (
        CheckConstraint("dose > 0", name="ck_prescription_dose_positive"),
        CheckConstraint(
            "frequency_times_per_day >= 1 AND frequency_times_per_day <= 6",
            name="ck_prescription_frequency_range",
        ),
        Index("ix_prescription_patient_id", "patient_id"),
        Index("ix_prescription_status", "status"),
        {"schema": MEDICATIONS_SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    medication_name = Column(String(200), nullable=False)
    dose = Column(Float, nullable=False)
    dose_unit = Column(String(20), nullable=False)
    frequency_times_per_day = Column(Integer, nullable=False)
    intake_schedule = Column(JSON, nullable=False)  # ["morning","afternoon","evening"]
    route = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    indication = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    prescribed_by = Column(
        Integer, ForeignKey("users.users.id"), nullable=True
    )  # null = самоназначение пациента
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    intakes = relationship(
        "MedicationIntake",
        back_populates="prescription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    patient = relationship("User", foreign_keys=[patient_id])


class MedicationIntake(Base):
    """Запись о фактическом приёме препарата."""

    __tablename__ = "medication_intakes"
    __table_args__ = (
        CheckConstraint("actual_dose > 0", name="ck_intake_dose_positive"),
        Index("ix_intake_prescription_id", "prescription_id"),
        Index("ix_intake_patient_id", "patient_id"),
        {"schema": MEDICATIONS_SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    prescription_id = Column(
        Integer,
        ForeignKey(
            f"{MEDICATIONS_SCHEMA}.medication_prescriptions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    patient_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    intake_datetime = Column(DateTime(timezone=True), nullable=False)
    actual_dose = Column(Float, nullable=False)
    intake_slot = Column(String(20), nullable=True)  # morning / afternoon / evening
    notes = Column(Text, nullable=True)
    is_retrospective = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    prescription = relationship("MedicationPrescription", back_populates="intakes")
    patient = relationship("User", foreign_keys=[patient_id])
