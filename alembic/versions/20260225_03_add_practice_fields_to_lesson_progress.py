"""Add practice_done and practice_completed_at to education.lesson_progress

Revision ID: 20260225_03
Revises: 20260225_02
Create Date: 2026-02-25

"""

import sqlalchemy as sa
from alembic import op

revision = "20260225_03"
down_revision = "20260225_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lesson_progress",
        sa.Column(
            "practice_done",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="education",
    )
    op.add_column(
        "lesson_progress",
        sa.Column(
            "practice_completed_at",
            sa.DateTime(),
            nullable=True,
        ),
        schema="education",
    )


def downgrade() -> None:
    op.drop_column("lesson_progress", "practice_completed_at", schema="education")
    op.drop_column("lesson_progress", "practice_done", schema="education")
