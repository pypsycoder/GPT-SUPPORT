"""Add diagnostics_json to llm_request_logs

Revision ID: 20260404_02
Revises: 20260404_01
Create Date: 2026-04-04

"""

import sqlalchemy as sa
from alembic import op

revision = "20260404_02"
down_revision = "20260404_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_request_logs",
        sa.Column(
            "diagnostics_json",
            sa.JSON(),
            nullable=True,
            comment="Pipeline diagnostics: stage status, fallbacks, context sizes, and RAG/provider signals.",
        ),
        schema="llm",
    )


def downgrade() -> None:
    op.drop_column("llm_request_logs", "diagnostics_json", schema="llm")
