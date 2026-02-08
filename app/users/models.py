"""SQLAlchemy models for user entities."""
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, JSON, String, text,
)
from sqlalchemy.sql import func

from app.models import Base


class User(Base):
    """User profile stored in the ``users`` schema."""

    __tablename__ = "users"
    __table_args__ = {"schema": "users"}

    id = Column(Integer, primary_key=True)
    full_name = Column(String)
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    consent_personal_data = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    consent_bot_use = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    consent_given_at = Column(DateTime(timezone=True), nullable=True)

    telegram_id = Column(String, unique=True, index=True, nullable=True)
    external_ids = Column(JSON, nullable=True)

    # веб-токен пациента для доступа к формам (legacy, сохраняем)
    patient_token = Column(String(64), unique=True, index=True, nullable=True)

    # --- PIN-авторизация ---
    patient_number = Column(Integer, unique=True, index=True, nullable=True)
    pin_hash = Column(String(128), nullable=True)
    pin_attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    is_locked = Column(Boolean, nullable=False, default=False, server_default=text("false"))
