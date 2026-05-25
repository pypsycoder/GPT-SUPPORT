"""Create patient_badges and patient_notifications tables

Revision ID: 20260303_00
Revises: 20260302_01
Create Date: 2026-03-03
"""

from alembic import op

revision = "20260303_00"
down_revision = "20260302_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS patient_badges (
            id          SERIAL PRIMARY KEY,
            patient_id  INTEGER NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
            badge_key   VARCHAR(50) NOT NULL,
            earned_at   TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(patient_id, badge_key)
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_patient_badges_patient_id
            ON patient_badges(patient_id);
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS patient_notifications (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id  INTEGER NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
            type        VARCHAR(50),
            icon        VARCHAR(10),
            title       VARCHAR(200),
            message     VARCHAR(500),
            action_url  VARCHAR(200),
            action_text VARCHAR(100),
            seen        BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_patient_notifications_patient_id
            ON patient_notifications(patient_id, seen, created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_patient_notifications_patient_id;")
    op.execute("DROP TABLE IF EXISTS patient_notifications;")
    op.execute("DROP INDEX IF EXISTS ix_patient_badges_patient_id;")
    op.execute("DROP TABLE IF EXISTS patient_badges;")