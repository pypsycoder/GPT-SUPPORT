"""Add auth session lifecycle and audit fields.

Revision ID: 20260404_01
Revises: 20260303_03
Create Date: 2026-04-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_01"
down_revision = "20260303_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        schema="users",
    )
    op.add_column(
        "sessions",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        schema="users",
    )
    op.add_column(
        "sessions",
        sa.Column("revoked_reason", sa.String(length=255), nullable=True),
        schema="users",
    )
    op.add_column(
        "sessions",
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        schema="users",
    )
    op.add_column(
        "sessions",
        sa.Column("last_seen_ip", sa.String(length=64), nullable=True),
        schema="users",
    )
    op.execute("UPDATE users.sessions SET last_seen_at = created_at WHERE last_seen_at IS NULL")
    op.alter_column(
        "sessions",
        "last_seen_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
        schema="users",
    )


def downgrade() -> None:
    op.drop_column("sessions", "last_seen_ip", schema="users")
    op.drop_column("sessions", "ip_address", schema="users")
    op.drop_column("sessions", "revoked_reason", schema="users")
    op.drop_column("sessions", "revoked_at", schema="users")
    op.drop_column("sessions", "last_seen_at", schema="users")
