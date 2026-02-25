from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models import Base

PRACTICES_SCHEMA = "practices"


class StandalonePractice(Base):
    __tablename__ = "practices"
    __table_args__ = {"schema": PRACTICES_SCHEMA}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    module_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    icf_domain: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    context: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    tagline: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    instruction: Mapped[list] = mapped_column(JSONB, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_prompt: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )



class PracticeCompletion(Base):
    __tablename__ = "practice_completions"
    __table_args__ = {"schema": PRACTICES_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    practice_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("practices.practices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    mood_after: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

