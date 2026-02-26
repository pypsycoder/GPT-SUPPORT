"""Add llm schema with chat_messages and llm_request_logs tables

Revision ID: 20260226_01
Revises: 20260225_03
Create Date: 2026-02-26

"""

import sqlalchemy as sa
from alembic import op

revision = "20260226_01"
down_revision = "20260225_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "llm"')

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_used", sa.String(length=60), nullable=True),
        sa.Column("domain", sa.String(length=40), nullable=True),
        sa.Column("request_type", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["users.users.id"],
            ondelete="CASCADE",
            name="fk_cm_patient_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="llm",
    )
    op.create_index(
        "ix_cm_patient_id", "chat_messages", ["patient_id"], schema="llm"
    )
    op.create_index(
        "ix_cm_created_at", "chat_messages", ["created_at"], schema="llm"
    )

    op.create_table(
        "llm_request_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=20), nullable=False),
        sa.Column("model_tier", sa.String(length=10), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_type", sa.String(length=40), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["users.users.id"],
            ondelete="CASCADE",
            name="fk_lrl_patient_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="llm",
    )
    op.create_index(
        "ix_lrl_patient_id", "llm_request_logs", ["patient_id"], schema="llm"
    )
    op.create_index(
        "ix_lrl_created_at", "llm_request_logs", ["created_at"], schema="llm"
    )
    op.create_index(
        "ix_lrl_account_id", "llm_request_logs", ["account_id"], schema="llm"
    )


def downgrade() -> None:
    op.drop_index("ix_lrl_account_id", table_name="llm_request_logs", schema="llm")
    op.drop_index("ix_lrl_created_at", table_name="llm_request_logs", schema="llm")
    op.drop_index("ix_lrl_patient_id", table_name="llm_request_logs", schema="llm")
    op.drop_table("llm_request_logs", schema="llm")

    op.drop_index("ix_cm_created_at", table_name="chat_messages", schema="llm")
    op.drop_index("ix_cm_patient_id", table_name="chat_messages", schema="llm")
    op.drop_table("chat_messages", schema="llm")

    op.execute('DROP SCHEMA IF EXISTS "llm"')
