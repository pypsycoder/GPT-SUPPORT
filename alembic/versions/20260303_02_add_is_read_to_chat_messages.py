"""Add is_read to llm.chat_messages for unread badge tracking

Revision ID: 20260303_02
Revises: 20260303_01
Create Date: 2026-03-03

Adds is_read BOOLEAN NOT NULL DEFAULT TRUE to llm.chat_messages.
Existing messages are treated as already read.
New assistant messages are saved with is_read=False and marked True
when the user opens the chat drawer.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260303_02"
down_revision = "20260303_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="False для непрочитанных сообщений ассистента",
        ),
        schema="llm",
    )
    op.create_index(
        "ix_cm_is_read",
        "chat_messages",
        ["patient_id", "is_read"],
        schema="llm",
    )


def downgrade() -> None:
    op.drop_index("ix_cm_is_read", table_name="chat_messages", schema="llm")
    op.drop_column("chat_messages", "is_read", schema="llm")
