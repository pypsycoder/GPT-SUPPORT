"""Add persistent supervisor state for patient chat

Revision ID: 20260228_02
Revises: 20260228_01
Create Date: 2026-02-28

"""

import sqlalchemy as sa
from alembic import op

revision = "20260228_02"
down_revision = "20260228_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_supervisor_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=80), nullable=False, server_default="default"),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["users.users.id"],
            ondelete="CASCADE",
            name="fk_css_patient_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id", "thread_id", name="uq_css_patient_thread"),
        schema="llm",
    )
    op.create_index(
        "ix_css_patient_id",
        "chat_supervisor_states",
        ["patient_id"],
        schema="llm",
    )


def downgrade() -> None:
    op.drop_index("ix_css_patient_id", table_name="chat_supervisor_states", schema="llm")
    op.drop_table("chat_supervisor_states", schema="llm")
