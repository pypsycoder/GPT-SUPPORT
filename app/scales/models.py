from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class ScaleResult(Base):
    """ORM-модель для хранения результатов прохождения шкал."""

    __tablename__ = "scale_results"
    __table_args__ = (
        Index("ix_scale_results_user_id", "user_id"),
        Index("ix_scale_results_scale_code", "scale_code"),
        Index("ix_scale_results_measured_at", "measured_at"),
        {"schema": "scales"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        Integer,
        ForeignKey("users.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    scale_code = Column(String(length=32), nullable=False)
    scale_version = Column(String(length=16), nullable=True)
    measured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    result_json = Column(JSON, nullable=False)
    answers_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ============================================================
# KDQOL-SF 1.3: measurement points + responses + subscale scores
# ============================================================

_KDQOL_SCHEMA = "kdqol"


class MeasurementPoint(Base):
    """Временная точка измерения T0/T1/T2, активируемая исследователем."""

    __tablename__ = "measurement_points"
    __table_args__ = (
        UniqueConstraint("patient_id", "point_type", name="uq_mp_patient_point_type"),
        CheckConstraint("point_type IN ('T0', 'T1', 'T2')", name="ck_mp_point_type"),
        Index("ix_mp_patient_id", "patient_id"),
        {"schema": _KDQOL_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.users.id", ondelete="CASCADE"), nullable=False
    )
    point_type: Mapped[str] = mapped_column(String(2), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    activated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.researchers.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    responses: Mapped[list[KdqolResponse]] = relationship(
        "KdqolResponse", back_populates="measurement_point", lazy="select"
    )
    subscale_scores: Mapped[list[KdqolSubscaleScore]] = relationship(
        "KdqolSubscaleScore", back_populates="measurement_point", lazy="select"
    )


class KdqolResponse(Base):
    """Индивидуальный ответ пациента на один вопрос KDQOL-SF."""

    __tablename__ = "kdqol_responses"
    __table_args__ = (
        Index("ix_kdqol_resp_mp_id", "measurement_point_id"),
        Index("ix_kdqol_resp_patient_id", "patient_id"),
        {"schema": _KDQOL_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.users.id", ondelete="CASCADE"), nullable=False
    )
    measurement_point_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{_KDQOL_SCHEMA}.measurement_points.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[str] = mapped_column(String(10), nullable=False)
    answer_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    measurement_point: Mapped[MeasurementPoint] = relationship(
        "MeasurementPoint", back_populates="responses"
    )


class KdqolSubscaleScore(Base):
    """Посчитанная субшкала (0-100) для конкретной точки измерения."""

    __tablename__ = "kdqol_subscale_scores"
    __table_args__ = (
        UniqueConstraint(
            "measurement_point_id", "subscale_name", name="uq_kdqol_score_mp_subscale"
        ),
        Index("ix_kdqol_score_patient_id", "patient_id"),
        {"schema": _KDQOL_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.users.id", ondelete="CASCADE"), nullable=False
    )
    measurement_point_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{_KDQOL_SCHEMA}.measurement_points.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscale_name: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    measurement_point: Mapped[MeasurementPoint] = relationship(
        "MeasurementPoint", back_populates="subscale_scores"
    )
