"""Add scales.scale_item_responses — normalized per-question scale answers (Фаза 5)

Revision ID: 20260917_01
Revises: 20260906_01
Create Date: 2026-09-17

Ответы по каждому вопросу HADS/KOP-25A/PSQI/PSS-10/WCQ уже пишутся в
scale_results.answers_json (JSON-блоб), но это неудобно для исследовательской
статистики по отдельным вопросам. Эта таблица — нормализованная копия, по
образцу kdqol.kdqol_responses, пишется ПАРАЛЛЕЛЬНО с answers_json (сам
контракт scale_results не меняется, чтобы не трогать production-ready модуль).
KDQOL-SF сюда не попадает — у неё уже есть kdqol.kdqol_responses.

См. docs/agent/PHASE5_RESEARCH_INSTRUMENTATION_SPEC.md (Track A).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917_01"
down_revision: Union[str, Sequence[str], None] = "20260906_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scale_item_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scale_code", sa.String(length=32), nullable=False),
        sa.Column("scale_version", sa.String(length=16), nullable=True),
        sa.Column("question_id", sa.String(length=64), nullable=False),
        sa.Column("answer_value", sa.String(length=255), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.users.id"],
            ondelete="CASCADE",
            name="fk_sir_user_id",
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["scales.scale_results.id"],
            ondelete="CASCADE",
            name="fk_sir_result_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="scales",
    )
    op.create_index(
        "ix_scale_item_responses_user_id",
        "scale_item_responses",
        ["user_id"],
        schema="scales",
    )
    op.create_index(
        "ix_scale_item_responses_result_id",
        "scale_item_responses",
        ["result_id"],
        schema="scales",
    )
    op.create_index(
        "ix_scale_item_responses_scale_code",
        "scale_item_responses",
        ["scale_code"],
        schema="scales",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scale_item_responses_scale_code", table_name="scale_item_responses", schema="scales"
    )
    op.drop_index(
        "ix_scale_item_responses_result_id", table_name="scale_item_responses", schema="scales"
    )
    op.drop_index(
        "ix_scale_item_responses_user_id", table_name="scale_item_responses", schema="scales"
    )
    op.drop_table("scale_item_responses", schema="scales")
