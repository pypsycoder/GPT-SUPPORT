"""Add prefix_fp to llm_call_log for prompt-prefix stability diagnostics

Revision ID: 20260809_03
Revises: 20260809_02
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260809_03'
down_revision: Union[str, Sequence[str], None] = '20260809_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'llm_call_log',
        sa.Column(
            'prefix_fp', sa.String(length=32), nullable=True,
            comment=(
                "PromptLayers.prefix_fingerprint() — отпечаток стабильной части промпта "
                "(system+profile+summary). Меняется чаще ожидаемого = утечка в префикс"
            ),
        ),
        schema='llm',
    )
    op.create_index('ix_lcl_prefix_fp', 'llm_call_log', ['prefix_fp'], schema='llm')


def downgrade() -> None:
    op.drop_index('ix_lcl_prefix_fp', table_name='llm_call_log', schema='llm')
    op.drop_column('llm_call_log', 'prefix_fp', schema='llm')
