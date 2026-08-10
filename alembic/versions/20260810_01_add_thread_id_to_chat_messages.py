"""Add thread_id to chat_messages so the prompt window is scoped to its thread

Revision ID: 20260810_01
Revises: 20260809_03
Create Date: 2026-08-10

Существующие строки получают 'default': до появления дебаг-чата все сообщения
писал только чат пациента, у которого thread_id == 'default'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260810_01'
down_revision: Union[str, Sequence[str], None] = '20260809_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'chat_messages',
        sa.Column(
            'thread_id', sa.String(length=64), nullable=False, server_default='default',
            comment=(
                "Тред диалога: 'default' — чат пациента, 'debug-*' — песочница исследователя. "
                "Окно диалога в промпте собирается только по своему треду"
            ),
        ),
        schema='llm',
    )
    op.create_index(
        'ix_cm_patient_thread', 'chat_messages', ['patient_id', 'thread_id'], schema='llm'
    )


def downgrade() -> None:
    op.drop_index('ix_cm_patient_thread', table_name='chat_messages', schema='llm')
    op.drop_column('chat_messages', 'thread_id', schema='llm')
