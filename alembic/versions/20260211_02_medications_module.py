"""Medications module: reference, medications, history, intakes, settings.

Revision ID: 20260211_02
Revises: 20260211_01
Create Date: 2026-02-11

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260211_02"
down_revision: Union[str, Sequence[str], None] = "20260211_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS medications")

    op.create_table(
        "medication_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name_ru", sa.String(length=200), nullable=False),
        sa.Column("name_trade", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("typical_doses", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("food_relation_hint", sa.String(length=20), nullable=True),
        sa.Column("search_keywords", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="medications",
    )
    op.create_index(
        "ix_medication_references_name_ru",
        "medication_references",
        ["name_ru"],
        schema="medications",
    )
    op.create_index(
        "ix_medication_references_category",
        "medication_references",
        ["category"],
        schema="medications",
    )

    op.create_table(
        "medications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("custom_name", sa.String(length=200), nullable=True),
        sa.Column("dose", sa.String(length=100), nullable=False),
        sa.Column("frequency_type", sa.String(length=20), nullable=False),
        sa.Column("days_of_week", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("times_of_day", postgresql.ARRAY(sa.Time()), nullable=False),
        sa.Column("relation_to_food", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint(
            "(reference_id IS NOT NULL) OR (custom_name IS NOT NULL)",
            name="ck_medication_has_name",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reference_id"], ["medications.medication_references.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="medications",
    )
    op.create_index(
        "ix_medications_user_id",
        "medications",
        ["user_id"],
        schema="medications",
    )
    op.create_index(
        "ix_medications_is_active",
        "medications",
        ["is_active"],
        schema="medications",
    )

    op.create_table(
        "medication_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("medication_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dose", sa.String(length=100), nullable=False),
        sa.Column("frequency_type", sa.String(length=20), nullable=False),
        sa.Column("days_of_week", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("times_of_day", postgresql.ARRAY(sa.Time()), nullable=False),
        sa.Column("relation_to_food", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("change_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.medications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="medications",
    )
    op.create_index(
        "ix_medication_history_medication_id",
        "medication_history",
        ["medication_id"],
        schema="medications",
    )

    op.create_table(
        "medication_intakes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("medication_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("scheduled_time", sa.Time(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.medications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "medication_id",
            "scheduled_date",
            "scheduled_time",
            name="uq_medication_intake_slot",
        ),
        schema="medications",
    )
    op.create_index(
        "ix_medication_intake_date",
        "medication_intakes",
        ["scheduled_date"],
        schema="medications",
    )

    op.create_table(
        "user_medication_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tracking_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        schema="medications",
    )


def downgrade() -> None:
    op.drop_table("user_medication_settings", schema="medications")
    op.drop_index("ix_medication_intake_date", table_name="medication_intakes", schema="medications")
    op.drop_constraint(
        "uq_medication_intake_slot",
        "medication_intakes",
        type_="unique",
        schema="medications",
    )
    op.drop_table("medication_intakes", schema="medications")
    op.drop_index("ix_medication_history_medication_id", table_name="medication_history", schema="medications")
    op.drop_table("medication_history", schema="medications")
    op.drop_index("ix_medications_is_active", table_name="medications", schema="medications")
    op.drop_index("ix_medications_user_id", table_name="medications", schema="medications")
    op.drop_table("medications", schema="medications")
    op.drop_index("ix_medication_references_category", table_name="medication_references", schema="medications")
    op.drop_index("ix_medication_references_name_ru", table_name="medication_references", schema="medications")
    op.drop_table("medication_references", schema="medications")
    op.execute("DROP SCHEMA IF EXISTS medications")
