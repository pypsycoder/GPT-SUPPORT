"""
SQLAlchemy ORM модели для LLM-модуля.

Схема: llm
Таблицы:
  - chat_messages        — история сообщений пациента и ассистента
  - llm_request_logs     — технический лог каждого запроса к GigaChat API (агрегат на ход пайплайна)
  - llm_call_log         — сырой лог каждого вызова GigaChat API (телеметрия кэша, см. TOKEN_OPTIMIZATION_PLAN)
  - patient_facts        — семантическая память: устойчивые факты о пациенте (см. app.llm.memory_store)
  - patient_fact_history — аудит изменений patient_facts
  - chat_summaries       — эпизодическая память: свёртка вытесненных из окна ходов
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

    thread_id: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        server_default="default",
        index=True,
        comment=(
            "Тред диалога: 'default' — чат пациента, 'debug-*' — песочница исследователя. "
            "Окно диалога в промпте собирается только по своему треду"
        ),
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


class ChatSupervisorState(Base):
    """Current supervisor state for the single patient chat."""

    __tablename__ = "chat_supervisor_states"
    __table_args__ = (
        sa.UniqueConstraint("patient_id", "thread_id", name="uq_css_patient_thread"),
        {"schema": "llm"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    patient_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.users.id", ondelete="CASCADE", name="fk_css_patient_id"),
        nullable=False,
        index=True,
    )

    thread_id: Mapped[str] = mapped_column(
        sa.String(80),
        nullable=False,
        server_default="default",
    )

    state_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.text("NOW()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.text("NOW()"),
        onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return f"<ChatSupervisorState id={self.id} patient={self.patient_id} thread={self.thread_id}>"


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

    diagnostics_json: Mapped[dict | None] = mapped_column(
        sa.JSON,
        nullable=True,
        comment="Pipeline diagnostics: stage status, fallbacks, context sizes, and RAG/provider signals.",
    )

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


class LLMCallLog(Base):
    """Сырой лог каждого вызова GigaChat API — для расчёта cache_hit и оплачиваемых токенов.

    В отличие от ``LLMRequestLog`` (один агрегат на весь ход пайплайна),
    здесь одна строка на один фактический HTTP-вызов ``GigaChatClient.call()``.
    """

    __tablename__ = "llm_call_log"
    __table_args__ = {"schema": "llm"}

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    patient_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.users.id", ondelete="SET NULL", name="fk_lcl_patient_id"),
        nullable=True,
    )

    step: Mapped[str | None] = mapped_column(
        sa.String(40),
        nullable=True,
        comment="parser | supervisor | router | summarizer | ...",
    )

    session_key: Mapped[str | None] = mapped_column(
        sa.String(120),
        nullable=True,
        comment="Значение заголовка X-Session-ID: f'p{patient_id}-{thread_id}'",
    )

    prefix_fp: Mapped[str | None] = mapped_column(
        sa.String(32),
        nullable=True,
        comment=(
            "PromptLayers.prefix_fingerprint() — отпечаток стабильной части промпта "
            "(system+profile+summary). Меняется чаще ожидаемого = утечка в префикс"
        ),
    )

    account_id: Mapped[str] = mapped_column(sa.String(20), nullable=False)

    model: Mapped[str] = mapped_column(sa.String(60), nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    completion_tokens: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    precached_tokens: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default="0",
        comment="usage.precached_prompt_tokens — токены, взятые из серверного кэша GigaChat",
    )

    total_tokens: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    latency_ms: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    finish_reason: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)

    ok: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default="true"
    )

    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.text("NOW()"),
    )

    def __repr__(self) -> str:
        return (
            f"<LLMCallLog id={self.id} account={self.account_id} step={self.step} "
            f"precached={self.precached_tokens}>"
        )


class PatientFact(Base):
    """Устойчивый факт о пациенте (семантическая память, слой [1] промпта).

    Идентичность факта — по ``normalized_key``, а не по ключу от модели:
    ``AgentReply.memory_candidates`` отдаёт произвольный текст без key/value
    (см. app.llm.agent.schemas), поэтому дедуп и решение о записи держит
    ``app.llm.memory_store`` детерминированно, по совпадению нормализованного
    текста между ходами.
    """

    __tablename__ = "patient_facts"
    __table_args__ = (
        sa.Index(
            "uq_patient_facts_active_key",
            "patient_id",
            "normalized_key",
            unique=True,
            postgresql_where=sa.text("status IN ('pending', 'active')"),
        ),
        sa.Index("ix_patient_facts_patient_status", "patient_id", "status"),
        {"schema": "llm"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    patient_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.users.id", ondelete="CASCADE", name="fk_pf_patient_id"),
        nullable=False,
    )

    text: Mapped[str] = mapped_column(sa.Text, nullable=False)

    normalized_key: Mapped[str] = mapped_column(sa.Text, nullable=False)

    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default="pending",
        comment="pending | active | superseded | retracted",
    )

    evidence_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")

    first_seen_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.text("NOW()")
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.text("NOW()")
    )

    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.text("NOW()")
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.text("NOW()"),
        onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return f"<PatientFact id={self.id} patient={self.patient_id} status={self.status}>"


class PatientFactHistory(Base):
    """Аудит изменений ``patient_facts`` — откуда взялось решение gate."""

    __tablename__ = "patient_fact_history"
    __table_args__ = (
        sa.Index("ix_pfh_fact_id", "fact_id"),
        {"schema": "llm"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    fact_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    patient_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    old_status: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)

    new_status: Mapped[str] = mapped_column(sa.String(20), nullable=False)

    reason: Mapped[str] = mapped_column(
        sa.String(40),
        nullable=False,
        comment="promoted | refreshed | capacity_evicted | expired",
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.text("NOW()")
    )

    def __repr__(self) -> str:
        return f"<PatientFactHistory fact={self.fact_id} {self.old_status}->{self.new_status}>"


class ChatSummary(Base):
    """Эпизодическая память: свёртка ходов, вытесненных из окна диалога (слой [2]).

    Симметрична ``ChatSupervisorState`` — один ряд на (patient_id, thread_id).
    ``covered_through_message_id`` — курсор по ``ChatMessage.id``: свёрнуты все
    ходы с id не больше этого значения, дальше их пересчитывать не нужно.
    """

    __tablename__ = "chat_summaries"
    __table_args__ = (
        sa.UniqueConstraint("patient_id", "thread_id", name="uq_cs_patient_thread"),
        {"schema": "llm"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    patient_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.users.id", ondelete="CASCADE", name="fk_cs_patient_id"),
        nullable=False,
        index=True,
    )

    thread_id: Mapped[str] = mapped_column(sa.String(80), nullable=False, server_default="default")

    digest: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="")

    covered_through_message_id: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )

    summarizer_version: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default="v1"
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.text("NOW()")
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        nullable=False,
        server_default=sa.text("NOW()"),
        onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return f"<ChatSummary patient={self.patient_id} thread={self.thread_id}>"


class ProactiveDelivery(Base):
    """Журнал проактивных доставок — единый дедуп координатора (Фаза 2).

    Одна строка на факт доставки одного проактивного сообщения. Координатор
    (``app.llm.proactive_coordinator``) перед отправкой смотрит, какие
    ``dedup_key`` уже отправлены пациенту за ``context_date``, и не повторяет
    их. Раньше каждая подсистема (morning / proactive / motivator) вела свой
    дедуп по ``chat_messages.request_type`` — общего потолка и общей защиты от
    дублей темы не было.

    ``dedup_key`` — стабильный идентификатор повода: ``morning``,
    ``anomaly:systolic_bp``, ``idle:sleep``, ``domain:emotion``, ``praise``.
    """

    __tablename__ = "proactive_deliveries"
    __table_args__ = (
        sa.UniqueConstraint(
            "patient_id", "context_date", "dedup_key", name="uq_pd_patient_date_key"
        ),
        sa.Index("ix_pd_patient_date", "patient_id", "context_date"),
        {"schema": "llm"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    patient_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.users.id", ondelete="CASCADE", name="fk_pd_patient_id"),
        nullable=False,
    )

    context_date: Mapped[datetime] = mapped_column(sa.Date, nullable=False)

    kind: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        comment="crisis | anomaly | misses | idle | praise | domain",
    )

    dedup_key: Mapped[str] = mapped_column(
        sa.String(60),
        nullable=False,
        comment="Стабильный идентификатор повода: 'morning', 'anomaly:systolic_bp', 'idle:sleep'",
    )

    domain: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)

    trigger: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        comment="login | cron_morning | cron_afternoon | cron_evening",
    )

    message_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("llm.chat_messages.id", ondelete="SET NULL", name="fk_pd_message_id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, server_default=sa.text("NOW()")
    )

    def __repr__(self) -> str:
        return (
            f"<ProactiveDelivery patient={self.patient_id} date={self.context_date} "
            f"key={self.dedup_key}>"
        )
