"""add patient_token to users

Revision ID: d2ca01903a4c
Revises: ab4dbdf64b6f
Create Date: 2025-11-26 19:19:06.735528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2ca01903a4c'
down_revision: Union[str, Sequence[str], None] = 'ab4dbdf64b6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("patient_token", sa.String(length=64), nullable=True),
        schema="users",
    )
    op.create_index(
        "ix_users_patient_token",
        "users",
        ["patient_token"],
        unique=True,
        schema="users",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_users_patient_token",
        table_name="users",
        schema="users",
    )
    op.drop_column(
        "users",
        "patient_token",
        schema="users",
    )
