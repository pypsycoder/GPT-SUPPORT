"""Add generated tsvector column for BM25-style full-text search on lesson chunks

Revision ID: 20260819_01
Revises: 20260810_01
Create Date: 2026-08-19

Заменяет кастомную лексическую эвристику (token overlap + ручной стеммер) в
app/rag/retriever.py на встроенный full-text search Postgres: GENERATED
колонка пересчитывается автоматически при вставке/обновлении chunk_text,
бэкфилл существующих строк выполняется самим ALTER TABLE.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '20260819_01'
down_revision: Union[str, Sequence[str], None] = '20260810_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE education.lesson_embeddings
        ADD COLUMN chunk_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('russian', chunk_text)) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX ix_lesson_embeddings_chunk_tsv
            ON education.lesson_embeddings USING GIN (chunk_tsv)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS education.ix_lesson_embeddings_chunk_tsv")
    op.execute("ALTER TABLE education.lesson_embeddings DROP COLUMN IF EXISTS chunk_tsv")
