"""Add llm.proactive_deliveries — unified proactive dedup ledger (Phase 2 coordinator)

Revision ID: 20260829_01
Revises: 20260820_01
Create Date: 2026-08-29

Единый дедуп-леджер проактивного координатора (см.
app/llm/proactive_coordinator.py). Раньше каждая подсистема (morning / proactive /
motivator) вела свой дедуп по chat_messages.request_type — общего потолка на день
и защиты от повтора темы не было.

Одна строка = один факт доставки одного проактивного сообщения.
UNIQUE (patient_id, context_date, dedup_key) — повод не повторяется за день.
FK пишем руками: cross-schema FK autogenerate не умеет (см. alembic/env.py).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_01"
down_revision: Union[str, Sequence[str], None] = "20260820_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proactive_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("context_date", sa.Date(), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            comment="crisis | anomaly | misses | idle | praise | domain",
        ),
        sa.Column(
            "dedup_key",
            sa.String(length=60),
            nullable=False,
            comment="Стабильный идентификатор повода: 'morning', 'anomaly:systolic_bp', 'idle:sleep'",
        ),
        sa.Column("domain", sa.String(length=40), nullable=True),
        sa.Column(
            "trigger",
            sa.String(length=20),
            nullable=False,
            comment="login | cron_morning | cron_afternoon | cron_evening",
        ),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["users.users.id"],
            ondelete="CASCADE",
            name="fk_pd_patient_id",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["llm.chat_messages.id"],
            ondelete="SET NULL",
            name="fk_pd_message_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "patient_id", "context_date", "dedup_key", name="uq_pd_patient_date_key"
        ),
        schema="llm",
    )
    op.create_index(
        "ix_pd_patient_date",
        "proactive_deliveries",
        ["patient_id", "context_date"],
        schema="llm",
    )


def downgrade() -> None:
    op.drop_index("ix_pd_patient_date", table_name="proactive_deliveries", schema="llm")
    op.drop_table("proactive_deliveries", schema="llm")
