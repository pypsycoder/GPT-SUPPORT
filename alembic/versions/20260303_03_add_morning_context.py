"""Add patient_daily_context table and buttons_json to llm.chat_messages

Revision ID: 20260303_03
Revises: 20260303_02
Create Date: 2026-03-03

Changes:
- llm.chat_messages: ADD COLUMN buttons_json JSONB (inline-кнопки для morning-сообщений)
- llm.patient_daily_context: новая таблица для хранения дневного контекста и флага отправки
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "20260303_03"
down_revision = "20260303_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Добавляем buttons_json в llm.chat_messages
    op.add_column(
        "chat_messages",
        sa.Column("buttons_json", postgresql.JSONB(), nullable=True),
        schema="llm",
    )

    # 2. Таблица дневного контекста пациента
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm.patient_daily_context (
            id           SERIAL PRIMARY KEY,
            patient_id   INTEGER NOT NULL
                             REFERENCES users.users(id) ON DELETE CASCADE,
            context_date DATE NOT NULL,
            context_json JSONB NOT NULL,
            message_sent BOOLEAN NOT NULL DEFAULT FALSE,
            message_id   INTEGER
                             REFERENCES llm.chat_messages(id) ON DELETE SET NULL,
            created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            UNIQUE (patient_id, context_date)
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_daily_ctx_patient_date
            ON llm.patient_daily_context (patient_id, context_date);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS llm.ix_daily_ctx_patient_date;")
    op.execute("DROP TABLE IF EXISTS llm.patient_daily_context;")
    op.drop_column("chat_messages", "buttons_json", schema="llm")
