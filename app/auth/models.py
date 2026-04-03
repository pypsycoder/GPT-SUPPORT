"""Session models for authentication."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func, CheckConstraint

from app.models import Base


class Session(Base):
    """Session storage for authenticated users and researchers."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("user_id IS NOT NULL OR researcher_id IS NOT NULL"),
        {"schema": "users"},
    )

    # Primary key
    token = Column(String(64), primary_key=True)

    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.users.id", ondelete="CASCADE"), nullable=True)
    researcher_id = Column(
        Integer, ForeignKey("users.researchers.id", ondelete="CASCADE"), nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Optional audit info
    user_agent = Column(String(512), nullable=True)

    def is_expired(self) -> bool:
        """Check if session has expired."""
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= expires_at

    def __repr__(self) -> str:
        return (
            f"<Session token_hash={self.token[:10]}... "
            f"user_id={self.user_id} researcher_id={self.researcher_id}>"
        )
