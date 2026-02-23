"""add block_code to lessons

Revision ID: 20260216_04
Revises: 20260216_03
Create Date: 2026-02-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260216_04'
down_revision: Union[str, Sequence[str], None] = '20260216_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lessons',
        sa.Column('block_code', sa.String(50), nullable=True),
        schema='education',
    )
    op.create_index(
        'ix_lessons_block_code',
        'lessons',
        ['block_code'],
        schema='education',
    )


def downgrade() -> None:
    op.drop_index('ix_lessons_block_code', 'lessons', schema='education')
    op.drop_column('lessons', 'block_code', schema='education')
