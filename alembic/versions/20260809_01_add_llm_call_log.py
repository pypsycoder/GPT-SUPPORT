"""Add llm_call_log table for GigaChat cache telemetry

Revision ID: 20260809_01
Revises: 20260612_01
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260809_01'
down_revision: Union[str, Sequence[str], None] = '20260612_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_call_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=True),
        sa.Column(
            'step', sa.String(length=40), nullable=True,
            comment='parser | supervisor | router | summarizer | ...',
        ),
        sa.Column('account_id', sa.String(length=20), nullable=False),
        sa.Column('model', sa.String(length=60), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'precached_tokens', sa.Integer(), nullable=False, server_default='0',
            comment='usage.precached_prompt_tokens — токены, взятые из серверного кэша GigaChat',
        ),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('finish_reason', sa.String(length=40), nullable=True),
        sa.Column('ok', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(
            ['patient_id'], ['users.users.id'],
            ondelete='SET NULL', name='fk_lcl_patient_id',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema='llm',
    )
    op.create_index('ix_lcl_patient_id', 'llm_call_log', ['patient_id'], schema='llm')
    op.create_index('ix_lcl_created_at', 'llm_call_log', ['created_at'], schema='llm')
    op.create_index('ix_lcl_step', 'llm_call_log', ['step'], schema='llm')


def downgrade() -> None:
    op.drop_index('ix_lcl_step', table_name='llm_call_log', schema='llm')
    op.drop_index('ix_lcl_created_at', table_name='llm_call_log', schema='llm')
    op.drop_index('ix_lcl_patient_id', table_name='llm_call_log', schema='llm')
    op.drop_table('llm_call_log', schema='llm')
