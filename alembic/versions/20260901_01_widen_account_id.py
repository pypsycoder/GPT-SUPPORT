"""Widen llm.*.account_id VARCHAR(20) → VARCHAR(64)

Revision ID: 20260901_01
Revises: 20260830_01
Create Date: 2026-09-01

`account_id` в `llm.llm_request_logs` и `llm.llm_call_log` объявлен VARCHAR(20).
Для настоящих LLM-ходов туда пишется короткий id пула («A1-pro»), но для ранних
ответов boundary_guard — `early_response_source.upper()`, а он длиннее: например
`BOUNDARY_GUARD_MEDICAL_URGENT` (28), `BOUNDARY_GUARD_SAFETY_LLM` (25). Сейчас
`pipeline.py` режет строку `[:20]` перед вставкой (защита от 500), из-за чего в
аналитике источник раннего ответа обрезан. Расширяем до 64 и снимаем срез.

Данные не трогаем (ALTER TYPE с расширением длины — без USING, без потерь).
downgrade сузит обратно; строки длиннее 20 к тому моменту в БД быть не должно
(срез в коде вернётся вместе с откатом ревизии), но на всякий случай downgrade
предваряется усечением — иначе ALTER упадёт.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_01"
down_revision: Union[str, Sequence[str], None] = "20260830_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("llm_request_logs", "llm_call_log")


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(
            table,
            "account_id",
            existing_type=sa.String(length=20),
            type_=sa.String(length=64),
            existing_nullable=False,
            schema="llm",
        )


def downgrade() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        conn.execute(
            sa.text(
                f"UPDATE llm.{table} SET account_id = left(account_id, 20) "
                f"WHERE length(account_id) > 20"
            )
        )
        op.alter_column(
            table,
            "account_id",
            existing_type=sa.String(length=64),
            type_=sa.String(length=20),
            existing_nullable=False,
            schema="llm",
        )
