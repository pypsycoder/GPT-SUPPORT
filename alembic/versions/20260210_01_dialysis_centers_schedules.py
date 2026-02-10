"""Dialysis centers and schedules: centers, users.center_id, dialysis_schedules.

Revision ID: 20260210_01
Revises: a1b2c3d4e5f6
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260210_01"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    shift_enum = postgresql.ENUM("morning", "afternoon", "evening", name="shift_enum")
    shift_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "centers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("timezone", sa.String(), nullable=False, server_default="Europe/Moscow"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("users", sa.Column("center_id", postgresql.UUID(as_uuid=True), nullable=True), schema="users")
    op.create_foreign_key("fk_users_center_id_centers", "users", "centers", ["center_id"], ["id"], source_schema="users", referent_schema="public")

    op.create_table(
        "dialysis_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("weekdays", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("shift", postgresql.ENUM("morning", "afternoon", "evening", name="shift_enum", create_type=False), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("change_reason", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["patient_id"], ["users.users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.researchers.id"]),
        sa.ForeignKeyConstraint(["closed_by"], ["users.researchers.id"]),
    )
    op.create_index("one_active_schedule_per_patient", "dialysis_schedules", ["patient_id"], unique=True, postgresql_where=sa.text("valid_to IS NULL"))


def downgrade() -> None:
    op.drop_index("one_active_schedule_per_patient", table_name="dialysis_schedules", postgresql_where=sa.text("valid_to IS NULL"))
    op.drop_table("dialysis_schedules")
    op.drop_constraint("fk_users_center_id_centers", "users", schema="users", type_="foreignkey")
    op.drop_column("users", "center_id", schema="users")
    op.drop_table("centers")
    postgresql.ENUM("morning", "afternoon", "evening", name="shift_enum").drop(op.get_bind(), checkfirst=True)
