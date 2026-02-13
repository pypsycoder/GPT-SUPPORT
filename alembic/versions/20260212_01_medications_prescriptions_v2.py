"""Medications v2: replace old tables with medication_prescriptions and medication_intakes.

Revision ID: 20260212_01
Revises: 20260211_02
Create Date: 2026-02-12

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260212_01"
down_revision: Union[str, Sequence[str], None] = "20260211_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS medications")

    # --- Drop old tables (order matters for FK) ---
    op.drop_table("medication_intakes", schema="medications")
    op.drop_table("medication_history", schema="medications")
    op.drop_table("user_medication_settings", schema="medications")
    op.drop_table("medications", schema="medications")
    op.drop_table("medication_references", schema="medications")

    # --- Create medication_prescriptions ---
    op.create_table(
        "medication_prescriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("medication_name", sa.String(length=200), nullable=False),
        sa.Column("dose", sa.Float(), nullable=False),
        sa.Column("dose_unit", sa.String(length=20), nullable=False),
        sa.Column("frequency_times_per_day", sa.Integer(), nullable=False),
        sa.Column("intake_schedule", sa.JSON(), nullable=False),
        sa.Column("route", sa.String(length=50), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("indication", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("prescribed_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["patient_id"], ["users.users.id"]),
        sa.ForeignKeyConstraint(["prescribed_by"], ["users.users.id"]),
        sa.CheckConstraint("dose > 0", name="ck_prescription_dose_positive"),
        sa.CheckConstraint(
            "frequency_times_per_day >= 1 AND frequency_times_per_day <= 6",
            name="ck_prescription_frequency_range",
        ),
        schema="medications",
    )
    op.create_index(
        "ix_prescription_patient_id",
        "medication_prescriptions",
        ["patient_id"],
        schema="medications",
    )
    op.create_index(
        "ix_prescription_status",
        "medication_prescriptions",
        ["status"],
        schema="medications",
    )

    # --- Create medication_intakes ---
    op.create_table(
        "medication_intakes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prescription_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("intake_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_dose", sa.Float(), nullable=False),
        sa.Column("intake_slot", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_retrospective", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["prescription_id"],
            ["medications.medication_prescriptions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["users.users.id"]),
        sa.CheckConstraint("actual_dose > 0", name="ck_intake_dose_positive"),
        schema="medications",
    )
    op.create_index(
        "ix_intake_prescription_id",
        "medication_intakes",
        ["prescription_id"],
        schema="medications",
    )
    op.create_index(
        "ix_intake_patient_id",
        "medication_intakes",
        ["patient_id"],
        schema="medications",
    )


def downgrade() -> None:
    op.drop_table("medication_intakes", schema="medications")
    op.drop_table("medication_prescriptions", schema="medications")
