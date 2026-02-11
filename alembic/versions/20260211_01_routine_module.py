"""Routine (d230) module: baseline, daily plans, verifications.

Revision ID: 20260211_01
Revises: 20260210_03
Create Date: 2026-02-11
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260211_01"
down_revision: Union[str, Sequence[str], None] = "20260210_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Схема для модуля рутины
    op.execute("CREATE SCHEMA IF NOT EXISTS routine")

    # baseline_routines
    op.create_table(
        "baseline_routines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("activity_pool", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("dialysis_day_template", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("non_dialysis_day_template", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("planning_time", sa.String(length=16), nullable=False),
        sa.Column("valid_from", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["users.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="routine",
    )
    op.create_index(
        "ix_baseline_routines_patient_id",
        "baseline_routines",
        ["patient_id"],
        schema="routine",
    )
    op.create_index(
        "one_active_baseline_per_patient",
        "baseline_routines",
        ["patient_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        schema="routine",
    )

    # daily_plans
    op.create_table(
        "daily_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("dialysis_day", sa.Boolean(), nullable=True),
        sa.Column("template_activities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("added_from_pool", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("custom_activities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("edit_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("retrospective_days", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["users.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="routine",
    )
    op.create_unique_constraint(
        "uq_daily_plans_patient_plan_date",
        "daily_plans",
        ["patient_id", "plan_date"],
        schema="routine",
    )
    op.create_index(
        "ix_daily_plans_patient_id",
        "daily_plans",
        ["patient_id"],
        schema="routine",
    )
    op.create_index(
        "ix_daily_plans_plan_date",
        "daily_plans",
        ["plan_date"],
        schema="routine",
    )

    # daily_verifications
    op.create_table(
        "daily_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("verification_date", sa.Date(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("dialysis_day", sa.Boolean(), nullable=True),
        sa.Column("template_executed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pool_added_executed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("custom_executed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("unplanned_executed", postgresql.ARRAY(sa.String(length=32)), nullable=True),
        sa.Column("custom_unplanned", sa.String(length=255), nullable=True),
        sa.Column("day_control_score", sa.Integer(), nullable=False),
        sa.Column("edit_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("retrospective_days", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["users.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["routine.daily_plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="routine",
    )
    op.create_unique_constraint(
        "uq_daily_verifications_patient_date",
        "daily_verifications",
        ["patient_id", "verification_date"],
        schema="routine",
    )
    op.create_index(
        "ix_daily_verifications_patient_id",
        "daily_verifications",
        ["patient_id"],
        schema="routine",
    )
    op.create_index(
        "ix_daily_verifications_date",
        "daily_verifications",
        ["verification_date"],
        schema="routine",
    )


def downgrade() -> None:
    op.drop_index("ix_daily_verifications_date", table_name="daily_verifications", schema="routine")
    op.drop_index("ix_daily_verifications_patient_id", table_name="daily_verifications", schema="routine")
    op.drop_constraint(
        "uq_daily_verifications_patient_date",
        "daily_verifications",
        type_="unique",
        schema="routine",
    )
    op.drop_table("daily_verifications", schema="routine")

    op.drop_index("ix_daily_plans_plan_date", table_name="daily_plans", schema="routine")
    op.drop_index("ix_daily_plans_patient_id", table_name="daily_plans", schema="routine")
    op.drop_constraint(
        "uq_daily_plans_patient_plan_date",
        "daily_plans",
        type_="unique",
        schema="routine",
    )
    op.drop_table("daily_plans", schema="routine")

    op.drop_index("one_active_baseline_per_patient", table_name="baseline_routines", schema="routine")
    op.drop_index("ix_baseline_routines_patient_id", table_name="baseline_routines", schema="routine")
    op.drop_table("baseline_routines", schema="routine")

    op.execute("DROP SCHEMA IF EXISTS routine")

