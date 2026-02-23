"""add is_onboarded to users

Revision ID: 20260223_01
Revises: 20260216_04
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260223_01'
down_revision: Union[str, Sequence[str], None] = '20260216_04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'is_onboarded',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
        schema='users',
    )


def downgrade() -> None:
    op.drop_column('users', 'is_onboarded', schema='users')
