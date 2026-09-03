"""Add public.app_settings — универсальное key/value для рантайм-тумблеров

Revision ID: 20260903_01
Revises: 20260901_01
Create Date: 2026-09-03

Настройки, которые меняются на живой системе без рестарта (в отличие от .env).
Первый потребитель — ключ ``llm_provider`` (``sber`` | ``cloudru``), переключатель
LLM-провайдера в researcher-панели (ROADMAP_AGENT.md Фаза 6).

Одна строка = одна настройка. Пусто = «берём значение из окружения».
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_01"
down_revision: Union[str, Sequence[str], None] = "20260901_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_by",
            sa.String(length=128),
            nullable=True,
            comment="кто менял (researcher.username)",
        ),
        sa.PrimaryKeyConstraint("key"),
        schema="public",
    )


def downgrade() -> None:
    op.drop_table("app_settings", schema="public")
