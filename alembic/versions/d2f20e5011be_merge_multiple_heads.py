"""Merge multiple heads

Revision ID: d2f20e5011be
Revises: 86a0d2c1f8e3, a515d149cfa3
Create Date: 2025-11-18 23:45:51.370161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2f20e5011be'
down_revision: Union[str, Sequence[str], None] = ('86a0d2c1f8e3', 'a515d149cfa3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
