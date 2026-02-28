"""Add education.lesson_embeddings table for Hybrid RAG

Revision ID: 20260228_01
Revises: 20260226_01
Create Date: 2026-02-28

Embeddings stored as TEXT (JSON array string) — no pgvector required.
"""

from alembic import op

revision = "20260228_01"
down_revision = "20260226_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Таблица эмбеддингов карточек уроков
    op.execute("""
        CREATE TABLE education.lesson_embeddings (
            id          SERIAL PRIMARY KEY,
            lesson_id   INTEGER NOT NULL
                            REFERENCES education.lessons(id) ON DELETE CASCADE,
            card_index  INTEGER NOT NULL,
            chunk_text  TEXT NOT NULL,
            embedding   TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Индекс для быстрого поиска по lesson_id
    op.execute("""
        CREATE INDEX ix_lesson_embeddings_lesson_id
            ON education.lesson_embeddings (lesson_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS education.lesson_embeddings")
