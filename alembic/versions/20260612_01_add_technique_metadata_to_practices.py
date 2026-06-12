"""add_technique_metadata_to_practices

Revision ID: 20260612_01
Revises: 20260228_02
Create Date: 2026-06-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260612_01'
down_revision: Union[str, Sequence[str], None] = '20260228_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('practices', sa.Column('emotion_tags', sa.ARRAY(sa.String()), nullable=True), schema='practices')
    op.add_column('practices', sa.Column('arousal_level', sa.String(length=20), nullable=True), schema='practices')
    op.add_column('practices', sa.Column('dialysis_ok', sa.Boolean(), nullable=True), schema='practices')
    op.add_column('practices', sa.Column('mechanism', sa.Text(), nullable=True), schema='practices')


def downgrade() -> None:
    op.drop_column('practices', 'mechanism', schema='practices')
    op.drop_column('practices', 'dialysis_ok', schema='practices')
    op.drop_column('practices', 'arousal_level', schema='practices')
    op.drop_column('practices', 'emotion_tags', schema='practices')
