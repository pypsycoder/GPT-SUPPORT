"""Add context to vitals measurements

Revision ID: ab4dbdf64b6f
Revises: 081c2bd2642c
Create Date: 2025-11-18 23:51:27.284667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab4dbdf64b6f'
down_revision: Union[str, Sequence[str], None] = '081c2bd2642c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # Добавляем context в витальные показатели

    # давление
    op.add_column(
        "bp_measurements",
        sa.Column(
            "context",
            sa.String(length=32),
            nullable=False,
            server_default="na",  # временный default для уже существующих строк
        ),
        schema="vitals",
    )

    # пульс
    op.add_column(
        "pulse_measurements",
        sa.Column(
            "context",
            sa.String(length=32),
            nullable=False,
            server_default="na",
        ),
        schema="vitals",
    )

    # вес
    op.add_column(
        "weight_measurements",
        sa.Column(
            "context",
            sa.String(length=32),
            nullable=False,
            server_default="na",
        ),
        schema="vitals",
    )

    # убираем server_default, дальше значение всегда задаёт приложение
    op.alter_column(
        "bp_measurements",
        "context",
        server_default=None,
        schema="vitals",
    )
    op.alter_column(
        "pulse_measurements",
        "context",
        server_default=None,
        schema="vitals",
    )
    op.alter_column(
        "weight_measurements",
        "context",
        server_default=None,
        schema="vitals",
    )


def downgrade() -> None:
    # Откат — просто убрать колонку context из всех трёх таблиц
    op.drop_column("weight_measurements", "context", schema="vitals")
    op.drop_column("pulse_measurements", "context", schema="vitals")
    op.drop_column("bp_measurements", "context", schema="vitals")
