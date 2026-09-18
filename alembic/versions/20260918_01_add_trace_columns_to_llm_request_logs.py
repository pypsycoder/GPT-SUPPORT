"""Add response_source/technique_id/safety_level to llm.llm_request_logs (Фаза 5 Track B)

Revision ID: 20260918_01
Revises: 20260917_01
Create Date: 2026-09-18

llm_request_logs уже пишется раз на ход пайплайна и уже содержит колонку
diagnostics_json — просто никогда не заполняется на боевом пути
(LLMPipeline._log_to_database). Вместо новой таблицы-трассы: заполняем
diagnostics_json (весь context.diagnostics — сырые решения каждой стадии) и
добавляем три плоские колонки для быстрой фильтрации/статистики поверх него.
Реактивный (/api/chat/message) и LLM-проактивный
(proactive_coordinator._render_via_pipeline) пути оба идут через один и тот же
LLMPipeline.process(), так что оба покрываются без отдельных правок.

См. docs/agent/PHASE5_RESEARCH_INSTRUMENTATION_SPEC.md (Track B).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_01"
down_revision: Union[str, Sequence[str], None] = "20260917_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_request_logs",
        sa.Column("response_source", sa.String(length=40), nullable=True),
        schema="llm",
    )
    op.add_column(
        "llm_request_logs",
        sa.Column("technique_id", sa.String(length=64), nullable=True),
        schema="llm",
    )
    op.add_column(
        "llm_request_logs",
        sa.Column("safety_level", sa.String(length=16), nullable=True),
        schema="llm",
    )


def downgrade() -> None:
    op.drop_column("llm_request_logs", "safety_level", schema="llm")
    op.drop_column("llm_request_logs", "technique_id", schema="llm")
    op.drop_column("llm_request_logs", "response_source", schema="llm")
