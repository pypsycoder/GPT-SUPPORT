"""add scale_results table for scales module

Revision ID: 3d3b0b2c7bf8
Revises: 86a0d2c1f8e3
Create Date: 2025-02-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3d3b0b2c7bf8"
down_revision: Union[str, Sequence[str], None] = "86a0d2c1f8e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA = "scales"


def upgrade() -> None:
    """Create schema and scale_results table."""

    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')

    op.create_table(
        "scale_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scale_code", sa.String(length=32), nullable=False),
        sa.Column("scale_version", sa.String(length=16), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("answers_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_scale_results_user_id",
        "scale_results",
        ["user_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_scale_results_scale_code",
        "scale_results",
        ["scale_code"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_scale_results_measured_at",
        "scale_results",
        ["measured_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Drop scale_results table."""

    op.drop_index("ix_scale_results_measured_at", table_name="scale_results", schema=SCHEMA)
    op.drop_index("ix_scale_results_scale_code", table_name="scale_results", schema=SCHEMA)
    op.drop_index("ix_scale_results_user_id", table_name="scale_results", schema=SCHEMA)
    op.drop_table("scale_results", schema=SCHEMA)
