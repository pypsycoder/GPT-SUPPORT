"""Add dialysis shift times to public.centers

Revision ID: 20260906_01
Revises: 20260903_01
Create Date: 2026-09-06

Каждый диализный центр работает по сменам в фиксированные часы. Пациент привязан
к смене через ``dialysis_schedules.shift`` (morning | afternoon | evening), а
часы самой смены — свойство центра. Эти 6 колонок дают окно диализа для дня:
``centers.<shift>_start .. centers.<shift>_end``.

Дефолты соответствуют графику центра исследования:
    morning   08:00–11:00
    afternoon 13:00–17:00
    evening   18:00–21:00
Существующие центры бэкфиллятся дефолтами; форма центра в researcher-панели
требует все шесть значений явно (строгая валидация порядка).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_01"
down_revision: Union[str, Sequence[str], None] = "20260903_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = (
    ("morning_start", "08:00"),
    ("morning_end", "11:00"),
    ("afternoon_start", "13:00"),
    ("afternoon_end", "17:00"),
    ("evening_start", "18:00"),
    ("evening_end", "21:00"),
)


def upgrade() -> None:
    for name, default in _COLUMNS:
        op.add_column(
            "centers",
            sa.Column(
                name,
                sa.Time(),
                nullable=False,
                server_default=sa.text(f"'{default}'"),
            ),
            schema="public",
        )


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("centers", name, schema="public")
