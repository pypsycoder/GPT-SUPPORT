"""SQLAlchemy models for user entities."""
from sqlalchemy import Boolean, Column, Integer, JSON, String, text

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
    telegram_id = Column(String, unique=True, nullable=False)
    external_ids = Column(JSON, nullable=True)
