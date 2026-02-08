"""Resolve conflicting migration heads - merge f1a2b3c4d5e6 and d2f20e5011be

Revision ID: h8i9j0k1l2m3
Revises: f1a2b3c4d5e6, d2f20e5011be
Create Date: 2026-02-08 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = ("f1a2b3c4d5e6", "d2f20e5011be")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge conflicting heads - no-op."""
    pass


def downgrade() -> None:
    """Downgrade merge - no-op."""
    pass
