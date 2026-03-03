"""
SQLAlchemy ORM модели для LLM-модуля.

Схема: llm
Таблицы:
  - chat_messages        — история сообщений пациента и ассистента
  - llm_request_logs     — технический лог каждого запроса к GigaChat API
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ChatMessage(Base):
    """Сообщение в чате: user или assistant."""

    __tablename__ = "chat_messages"
    __table_args__ = {"schema": "llm"}

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    patient_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.users.id", ondelete="CASCADE", name="fk_cm_patient_id"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        comment="user | assistant",
    )

    content: Mapped[str] = mapped_column(sa.Text, nullable=False)

    tokens_used: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    model_used: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)

    domain: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)

    request_type: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)

    is_read: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default="true",
        comment="False для непрочитанных сообщений ассистента",
    )

    buttons_json: Mapped[list | None] = mapped_column(
        sa.JSON,
        nullable=True,
        comment="Inline-кнопки для morning-сообщений [{label, action}]",
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.text("NOW()"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChatMessage id={self.id} patient={self.patient_id} role={self.role}>"
        )


class LLMRequestLog(Base):
    """Технический лог каждого запроса к GigaChat API."""

    __tablename__ = "llm_request_logs"
    __table_args__ = {"schema": "llm"}

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    patient_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.users.id", ondelete="CASCADE", name="fk_lrl_patient_id"),
        nullable=False,
        index=True,
    )

    account_id: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        comment="ID аккаунта GigaChat (A1, A2, ...)",
    )

    model_tier: Mapped[str] = mapped_column(
        sa.String(10),
        nullable=False,
        comment="lite | pro | max",
    )

    tokens_input: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    tokens_output: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    response_time_ms: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    request_type: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)

    success: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default="true"
    )

    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.text("NOW()"),
    )

    def __repr__(self) -> str:
        return (
            f"<LLMRequestLog id={self.id} account={self.account_id} "
            f"tier={self.model_tier} success={self.success}>"
        )
