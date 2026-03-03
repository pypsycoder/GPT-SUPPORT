"""Add level column to patient_badges and create patient_streaks table

Revision ID: 20260303_01
Revises: 20260303_00
Create Date: 2026-03-03

Changes:
- patient_badges: ADD COLUMN level INTEGER DEFAULT 1
- CREATE TABLE patient_streaks (patient_id, tracker, current_streak, best_streak, last_action_date)
"""

from alembic import op

revision = "20260303_01"
down_revision = "20260303_00"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем level в patient_badges (таблица в public схеме)
    op.execute("""
        ALTER TABLE patient_badges
            ADD COLUMN IF NOT EXISTS level INTEGER NOT NULL DEFAULT 1;
    """)

    # Таблица серий по трекерам
    op.execute("""
        CREATE TABLE IF NOT EXISTS patient_streaks (
            patient_id       INTEGER NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
            tracker          VARCHAR(30) NOT NULL,
            current_streak   INTEGER NOT NULL DEFAULT 0,
            best_streak      INTEGER NOT NULL DEFAULT 0,
            last_action_date DATE,
            PRIMARY KEY (patient_id, tracker)
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_patient_streaks_patient_id
            ON patient_streaks (patient_id);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_patient_streaks_patient_id;")
    op.execute("DROP TABLE IF EXISTS patient_streaks;")
    op.execute("""
        ALTER TABLE patient_badges DROP COLUMN IF EXISTS level;
    """)
