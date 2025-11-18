"""Split vitals into separate tables

Revision ID: 86a0d2c1f8e3
Revises: 980f6beb1f52
Create Date: 2025-02-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "86a0d2c1f8e3"
down_revision: Union[str, Sequence[str], None] = "980f6beb1f52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA = "vitals"


def upgrade() -> None:
    op.create_table(
        "bp_measurement",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.users.id"), nullable=False),
        sa.Column("systolic_mm_hg", sa.Integer(), nullable=False),
        sa.Column("diastolic_mm_hg", sa.Integer(), nullable=False),
        sa.Column("pulse_bpm", sa.Integer(), nullable=True),
        sa.Column("measured_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("context", sa.String(), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "fluid_intake_event",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.users.id"), nullable=False),
        sa.Column("volume_ml", sa.Integer(), nullable=False),
        sa.Column("intake_type", sa.String(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "weight_measurement",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.users.id"), nullable=False),
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=False),
        sa.Column("measured_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("context", sa.String(), nullable=True),
        schema=SCHEMA,
    )

    op.drop_table("measurements", schema=SCHEMA)


def downgrade() -> None:
    op.create_table(
        "measurements",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("bp_sys", sa.Integer(), nullable=True),
        sa.Column("bp_dia", sa.Integer(), nullable=True),
        sa.Column("pulse", sa.Integer(), nullable=True),
        sa.Column("fluid_intake", sa.Numeric(), nullable=True),
        sa.Column("measured_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.users.id"]),
        schema=SCHEMA,
    )

    op.drop_table("weight_measurement", schema=SCHEMA)
    op.drop_table("fluid_intake_event", schema=SCHEMA)
    op.drop_table("bp_measurement", schema=SCHEMA)
