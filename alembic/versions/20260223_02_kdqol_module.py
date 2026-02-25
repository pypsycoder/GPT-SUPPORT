"""kdqol module: measurement_points, kdqol_responses, kdqol_subscale_scores

Revision ID: 20260223_02
Revises: 20260223_01
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260223_02"
down_revision: Union[str, None] = "20260223_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create kdqol schema
    op.execute('CREATE SCHEMA IF NOT EXISTS "kdqol"')

    # measurement_points
    op.create_table(
        "measurement_points",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("point_type", sa.String(2), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("activated_by", sa.Integer(), sa.ForeignKey("users.researchers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("point_type IN ('T0', 'T1', 'T2')", name="ck_mp_point_type"),
        sa.UniqueConstraint("patient_id", "point_type", name="uq_mp_patient_point_type"),
        schema="kdqol",
    )
    op.create_index("ix_mp_patient_id", "measurement_points", ["patient_id"], schema="kdqol")

    # kdqol_responses
    op.create_table(
        "kdqol_responses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measurement_point_id", sa.Integer(), sa.ForeignKey("kdqol.measurement_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.String(10), nullable=False),
        sa.Column("answer_value", sa.Numeric(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="kdqol",
    )
    op.create_index("ix_kdqol_resp_mp_id", "kdqol_responses", ["measurement_point_id"], schema="kdqol")
    op.create_index("ix_kdqol_resp_patient_id", "kdqol_responses", ["patient_id"], schema="kdqol")

    # kdqol_subscale_scores
    op.create_table(
        "kdqol_subscale_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measurement_point_id", sa.Integer(), sa.ForeignKey("kdqol.measurement_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscale_name", sa.String(50), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("measurement_point_id", "subscale_name", name="uq_kdqol_score_mp_subscale"),
        schema="kdqol",
    )
    op.create_index("ix_kdqol_score_patient_id", "kdqol_subscale_scores", ["patient_id"], schema="kdqol")


def downgrade() -> None:
    op.drop_table("kdqol_subscale_scores", schema="kdqol")
    op.drop_table("kdqol_responses", schema="kdqol")
    op.drop_table("measurement_points", schema="kdqol")
    op.execute('DROP SCHEMA IF EXISTS "kdqol"')
