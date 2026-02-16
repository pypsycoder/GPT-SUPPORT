"""add actions_json to lesson_cards

Revision ID: 20260216_02
Revises: 20260212_01
Create Date: 2026-02-16 17:06:07.328447

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260216_02'
down_revision: Union[str, Sequence[str], None] = '20260212_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lesson_cards',
        sa.Column('actions_json', sa.Text(), nullable=True),
        schema='education',
    )


def downgrade() -> None:
    op.drop_column('lesson_cards', 'actions_json', schema='education')