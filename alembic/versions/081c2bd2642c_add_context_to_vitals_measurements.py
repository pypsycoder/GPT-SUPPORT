"""Add context to vitals measurements

Revision ID: 081c2bd2642c
Revises: d2f20e5011be
Create Date: 2025-11-18 23:46:18.436889

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '081c2bd2642c'
down_revision: Union[str, Sequence[str], None] = 'd2f20e5011be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
