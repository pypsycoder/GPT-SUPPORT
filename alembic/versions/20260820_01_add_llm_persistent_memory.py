"""Add persistent semantic (patient_facts) and episodic (chat_summaries) memory

Revision ID: 20260820_01
Revises: 20260819_01
Create Date: 2026-08-20

Персистентная память LLM-слоя (см. app/llm/pipeline/STRUCTURE.md, «Память»).
Working-память (chat_messages) и состояние хода (chat_supervisor_states) уже
персистентны — не хватало только семантической (устойчивые факты) и
эпизодической (свёртка вытесненных из окна ходов) памяти. См.
app/llm/memory_store.py.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_01"
down_revision: Union[str, Sequence[str], None] = "20260819_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patient_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "first_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["users.users.id"],
            ondelete="CASCADE",
            name="fk_pf_patient_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="llm",
    )
    op.create_index(
        "uq_patient_facts_active_key",
        "patient_facts",
        ["patient_id", "normalized_key"],
        unique=True,
        schema="llm",
        postgresql_where=sa.text("status IN ('pending', 'active')"),
    )
    op.create_index(
        "ix_patient_facts_patient_status",
        "patient_facts",
        ["patient_id", "status"],
        schema="llm",
    )

    op.create_table(
        "patient_fact_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fact_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("old_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        schema="llm",
    )
    op.create_index(
        "ix_pfh_fact_id", "patient_fact_history", ["fact_id"], schema="llm"
    )

    op.create_table(
        "chat_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=80), nullable=False, server_default="default"),
        sa.Column("digest", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "covered_through_message_id", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("summarizer_version", sa.String(length=20), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["users.users.id"],
            ondelete="CASCADE",
            name="fk_cs_patient_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id", "thread_id", name="uq_cs_patient_thread"),
        schema="llm",
    )
    op.create_index("ix_cs_patient_id", "chat_summaries", ["patient_id"], schema="llm")


def downgrade() -> None:
    op.drop_index("ix_cs_patient_id", table_name="chat_summaries", schema="llm")
    op.drop_table("chat_summaries", schema="llm")

    op.drop_index("ix_pfh_fact_id", table_name="patient_fact_history", schema="llm")
    op.drop_table("patient_fact_history", schema="llm")

    op.drop_index(
        "ix_patient_facts_patient_status", table_name="patient_facts", schema="llm"
    )
    op.drop_index(
        "uq_patient_facts_active_key", table_name="patient_facts", schema="llm"
    )
    op.drop_table("patient_facts", schema="llm")
