from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID

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
