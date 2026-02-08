"""SQLAlchemy model for researcher (исследователь) entity."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, text
from sqlalchemy.sql import func

from app.models import Base


class Researcher(Base):
    """Researcher account for managing patients and viewing data."""

    __tablename__ = "researchers"
    __table_args__ = {"schema": "users"}

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
