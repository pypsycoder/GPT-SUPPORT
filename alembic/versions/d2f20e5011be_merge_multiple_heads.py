"""Merge multiple heads (fixed chain)

Revision ID: d2f20e5011be
Revises: c9f0e1d2a3b4
Create Date: 2025-11-18 23:45:51.370161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2f20e5011be'
down_revision: Union[str, Sequence[str], None] = 'c9f0e1d2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
