"""Add session_key to llm_call_log for X-Session-ID cache diagnostics

Revision ID: 20260809_02
Revises: 20260809_01
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260809_02'
down_revision: Union[str, Sequence[str], None] = '20260809_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'llm_call_log',
        sa.Column(
            'session_key', sa.String(length=120), nullable=True,
            comment="Значение заголовка X-Session-ID: f'p{patient_id}-{thread_id}'",
        ),
        schema='llm',
    )
    op.create_index('ix_lcl_session_key', 'llm_call_log', ['session_key'], schema='llm')


def downgrade() -> None:
    op.drop_index('ix_lcl_session_key', table_name='llm_call_log', schema='llm')
    op.drop_column('llm_call_log', 'session_key', schema='llm')
