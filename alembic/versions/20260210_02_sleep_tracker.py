# ============================================
# Sleep Tracker: схема sleep и таблица sleep_records
# ============================================

"""sleep tracker schema and sleep_records table

Revision ID: 20260210_02
Revises: 20260210_01
Create Date: 2026-02-10

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260210_02"
down_revision: Union[str, Sequence[str], None] = "20260210_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS sleep")
    op.create_table(
        "sleep_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("late_entry", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("dialysis_day", sa.Boolean(), nullable=True),
        sa.Column("sleep_onset", sa.String(length=5), nullable=False),
        sa.Column("wake_time", sa.String(length=5), nullable=False),
        sa.Column("tib_minutes", sa.Integer(), nullable=False),
        sa.Column("tst_minutes", sa.Integer(), nullable=False),
        sa.Column("sleep_efficiency_pct", sa.Float(), nullable=False),
        sa.Column("night_awakenings", sa.String(length=8), nullable=False),
        sa.Column("sleep_latency", sa.String(length=8), nullable=False),
        sa.Column("morning_wellbeing", sa.String(length=20), nullable=False),
        sa.Column("daytime_nap", sa.String(length=12), nullable=True),
        sa.Column("sleep_disturbances", postgresql.ARRAY(sa.String()), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["users.users.id"], ondelete="CASCADE"),
        schema="sleep",
    )
    op.create_index("ix_sleep_records_patient_id", "sleep_records", ["patient_id"], schema="sleep")
    op.create_index("ix_sleep_records_submitted_at", "sleep_records", ["submitted_at"], schema="sleep")


def downgrade() -> None:
    op.drop_index("ix_sleep_records_submitted_at", table_name="sleep_records", schema="sleep")
    op.drop_index("ix_sleep_records_patient_id", table_name="sleep_records", schema="sleep")
    op.drop_table("sleep_records", schema="sleep")
    op.execute("DROP SCHEMA IF EXISTS sleep")
