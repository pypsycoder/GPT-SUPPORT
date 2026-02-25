"""Add practices schema with practices and practice_completions tables

Revision ID: 20260225_02
Revises: 20260225_01
Create Date: 2026-02-25

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "20260225_02"
down_revision = "20260225_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "practices"')

    op.create_table(
        "practices",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("module_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("icf_domain", sa.String(), nullable=True),
        sa.Column("context", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("tagline", sa.String(), nullable=True),
        sa.Column("instruction", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_prompt", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="practices",
    )
    op.create_index("ix_practices_module_id", "practices", ["module_id"], schema="practices")
    op.create_index("ix_practices_is_active", "practices", ["is_active"], schema="practices")

    op.create_table(
        "practice_completions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("practice_id", sa.String(), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("mood_after", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["users.users.id"],
            ondelete="CASCADE",
            name="fk_pc_patient_id",
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["practices.practices.id"],
            ondelete="CASCADE",
            name="fk_pc_practice_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="practices",
    )
    op.create_index(
        "ix_pc_patient_id", "practice_completions", ["patient_id"], schema="practices"
    )
    op.create_index(
        "ix_pc_practice_id", "practice_completions", ["practice_id"], schema="practices"
    )


def downgrade() -> None:
    op.drop_index("ix_pc_practice_id", table_name="practice_completions", schema="practices")
    op.drop_index("ix_pc_patient_id", table_name="practice_completions", schema="practices")
    op.drop_table("practice_completions", schema="practices")

    op.drop_index("ix_practices_is_active", table_name="practices", schema="practices")
    op.drop_index("ix_practices_module_id", table_name="practices", schema="practices")
    op.drop_table("practices", schema="practices")

    op.execute('DROP SCHEMA IF EXISTS "practices"')
