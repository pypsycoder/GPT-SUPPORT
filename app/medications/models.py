# ============================================
# Medications module: ORM models and enums
# ============================================
# Schema "medications". User ID is Integer (users.users.id).

from __future__ import annotations

from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import declared_attr, relationship

from app.models import Base

if False:
    from app.users.models import User


MEDICATIONS_SCHEMA = "medications"


# --- Enums (stored as strings in DB) ---


class MedicationCategory(str, Enum):
    """Категории препаратов для группировки и аналитики."""
    phosphate_binder = "phosphate_binder"
    antihypertensive = "antihypertensive"
    esa = "esa"
    iron = "iron"
    vitamin_d = "vitamin_d"
    calcimimetic = "calcimimetic"
    diuretic = "diuretic"
    anticoagulant = "anticoagulant"
    potassium_binder = "potassium_binder"
    other = "other"


class FrequencyType(str, Enum):
    """Тип частоты приёма."""
    daily = "daily"
    specific_days = "specific_days"


class FoodRelation(str, Enum):
    """Связь с приёмом пищи."""
    before = "before"
    with_meal = "with"
    after = "after"
    none = "none"


class IntakeStatus(str, Enum):
    """Статус приёма (только для MedicationIntake)."""
    taken = "taken"
    skipped = "skipped"


# --- MedicationReference ---


class MedicationReference(Base):
    """Справочник препаратов (предзаполнен, read-only для пациентов)."""

    __tablename__ = "medication_references"

    @declared_attr
    def __table_args__(cls):  # type: ignore[override]
        return (
            Index("ix_medication_references_name_ru", "name_ru"),
            Index("ix_medication_references_category", "category"),
            {"schema": MEDICATIONS_SCHEMA},
        )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name_ru = Column(String(200), nullable=False)
    name_trade = Column(String(500), nullable=True)
    category = Column(String(50), nullable=False)  # MedicationCategory
    typical_doses = Column(ARRAY(String), default=list)
    food_relation_hint = Column(String(20), nullable=True)  # FoodRelation
    search_keywords = Column(Text, nullable=True)
    sort_order = Column(Integer, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# --- Medication ---


class Medication(Base):
    """Препарат в схеме пациента."""

    __tablename__ = "medications"

    @declared_attr
    def __table_args__(cls):  # type: ignore[override]
        return (
            CheckConstraint(
                "(reference_id IS NOT NULL) OR (custom_name IS NOT NULL)",
                name="ck_medication_has_name",
            ),
            Index("ix_medications_user_id", "user_id"),
            Index("ix_medications_is_active", "is_active"),
            {"schema": MEDICATIONS_SCHEMA},
        )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)

    reference_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("medications.medication_references.id"),
        nullable=True,
    )
    custom_name = Column(String(200), nullable=True)

    dose = Column(String(100), nullable=False)
    frequency_type = Column(String(20), nullable=False)  # FrequencyType
    days_of_week = Column(ARRAY(Integer), nullable=True)  # 0=пн .. 6=вс
    times_of_day = Column(ARRAY(Time()), nullable=False)

    relation_to_food = Column(String(20), nullable=True)  # FoodRelation
    notes = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    reference = relationship("MedicationReference", lazy="joined", foreign_keys=[reference_id])
    user = relationship("User", back_populates="medications", foreign_keys=[user_id])
    history = relationship(
        "MedicationHistory",
        back_populates="medication",
        order_by="MedicationHistory.changed_at.desc()",
    )
    intakes = relationship("MedicationIntake", back_populates="medication")

    @property
    def display_name(self) -> str:
        """Название для отображения в UI."""
        if self.reference:
            return self.reference.name_ru
        return self.custom_name or "Без названия"


# --- MedicationHistory ---


class MedicationHistory(Base):
    """История изменений препарата."""

    __tablename__ = "medication_history"

    @declared_attr
    def __table_args__(cls):  # type: ignore[override]
        return (
            Index("ix_medication_history_medication_id", "medication_id"),
            {"schema": MEDICATIONS_SCHEMA},
        )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    medication_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("medications.medications.id", ondelete="CASCADE"),
        nullable=False,
    )

    dose = Column(String(100), nullable=False)
    frequency_type = Column(String(20), nullable=False)
    days_of_week = Column(ARRAY(Integer), nullable=True)
    times_of_day = Column(ARRAY(Time()), nullable=False)
    relation_to_food = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)

    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    change_reason = Column(String(500), nullable=True)

    medication = relationship("Medication", back_populates="history")


# --- MedicationIntake ---


class MedicationIntake(Base):
    """Запись о приёме/пропуске препарата."""

    __tablename__ = "medication_intakes"

    @declared_attr
    def __table_args__(cls):  # type: ignore[override]
        return (
            Index("ix_medication_intake_date", "scheduled_date"),
            UniqueConstraint(
                "medication_id",
                "scheduled_date",
                "scheduled_time",
                name="uq_medication_intake_slot",
            ),
            {"schema": MEDICATIONS_SCHEMA},
        )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    medication_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("medications.medications.id", ondelete="CASCADE"),
        nullable=False,
    )

    scheduled_date = Column(Date, nullable=False)
    scheduled_time = Column(Time(), nullable=False)
    status = Column(String(20), nullable=False)  # IntakeStatus
    taken_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medication = relationship("Medication", back_populates="intakes")


# --- UserMedicationSettings ---


class UserMedicationSettings(Base):
    """Настройки модуля лекарств для пользователя."""

    __tablename__ = "user_medication_settings"

    __table_args__ = {"schema": MEDICATIONS_SCHEMA}

    user_id = Column(
        Integer,
        ForeignKey("users.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tracking_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")
