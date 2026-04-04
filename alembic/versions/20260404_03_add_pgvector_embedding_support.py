"""Add pgvector support for education.lesson_embeddings

Revision ID: 20260404_03
Revises: 20260404_02
Create Date: 2026-04-04

"""

from alembic import op
from sqlalchemy import text

revision = "20260404_03"
down_revision = "20260404_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    extension_available = bool(
        bind.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_available_extensions
                    WHERE name = 'vector'
                )
                """
            )
        ).scalar()
    )
    if not extension_available:
        return

    bind.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    bind.execute(
        text(
            """
            ALTER TABLE education.lesson_embeddings
            ADD COLUMN IF NOT EXISTS embedding_vector vector(1024)
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE education.lesson_embeddings
            SET embedding_vector = CAST(embedding AS vector)
            WHERE embedding IS NOT NULL
              AND embedding_vector IS NULL
            """
        )
    )
    bind.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_lesson_embeddings_embedding_vector_ivfflat
                ON education.lesson_embeddings
                USING ivfflat (embedding_vector vector_cosine_ops)
                WITH (lists = 32)
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    vector_column_present = bool(
        bind.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'education'
                      AND table_name = 'lesson_embeddings'
                      AND column_name = 'embedding_vector'
                )
                """
            )
        ).scalar()
    )
    if not vector_column_present:
        return

    bind.execute(text("DROP INDEX IF EXISTS education.ix_lesson_embeddings_embedding_vector_ivfflat"))
    bind.execute(
        text(
            """
            ALTER TABLE education.lesson_embeddings
            DROP COLUMN IF EXISTS embedding_vector
            """
        )
    )
