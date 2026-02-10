# ============================================
# Sleep Tracker: sleep_date, updated_at, retrospective_days, edit_count, UNIQUE
# ============================================

"""add sleep_date updated_at retrospective_days edit_count unique constraint

Revision ID: 20260210_03
Revises: 20260210_02
Create Date: 2026-02-10

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260210_03"
down_revision: Union[str, Sequence[str], None] = "20260210_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sleep_records",
        sa.Column("sleep_date", sa.Date(), nullable=True),
        schema="sleep",
    )
    op.add_column(
        "sleep_records",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        schema="sleep",
    )
    op.add_column(
        "sleep_records",
        sa.Column("retrospective_days", sa.Integer(), nullable=True),
        schema="sleep",
    )
    op.add_column(
        "sleep_records",
        sa.Column("edit_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema="sleep",
    )
    # Backfill: sleep_date = submitted_at::date - 1, updated_at = submitted_at, retrospective_days = 1
    op.execute("""
        UPDATE sleep.sleep_records
        SET
            sleep_date = ((submitted_at AT TIME ZONE 'UTC')::date - 1),
            updated_at = submitted_at,
            retrospective_days = 1
        WHERE sleep_date IS NULL
    """)
    op.alter_column(
        "sleep_records",
        "sleep_date",
        existing_type=sa.Date(),
        nullable=False,
        schema="sleep",
    )
    op.alter_column(
        "sleep_records",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
        schema="sleep",
    )
    op.create_unique_constraint(
        "uq_sleep_records_patient_sleep_date",
        "sleep_records",
        ["patient_id", "sleep_date"],
        schema="sleep",
    )
    op.create_index(
        "ix_sleep_records_sleep_date",
        "sleep_records",
        ["sleep_date"],
        schema="sleep",
    )


def downgrade() -> None:
    op.drop_index("ix_sleep_records_sleep_date", table_name="sleep_records", schema="sleep")
    op.drop_constraint(
        "uq_sleep_records_patient_sleep_date",
        "sleep_records",
        type_="unique",
        schema="sleep",
    )
    op.drop_column("sleep_records", "edit_count", schema="sleep")
    op.drop_column("sleep_records", "retrospective_days", schema="sleep")
    op.drop_column("sleep_records", "updated_at", schema="sleep")
    op.drop_column("sleep_records", "sleep_date", schema="sleep")
