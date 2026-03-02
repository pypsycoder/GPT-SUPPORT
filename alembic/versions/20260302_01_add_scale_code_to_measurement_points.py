"""Add scale_code to kdqol.measurement_points for unified T0/T1/T2 trigger

Revision ID: 20260302_01
Revises: 20260228_01
Create Date: 2026-03-02

Extends measurement_points to support multiple scales (KDQOL_SF, WCQ_LAZARUS, KOP_25A).
- Adds scale_code VARCHAR(20) NOT NULL DEFAULT 'KDQOL_SF'
- Drops old unique constraint (patient_id, point_type)
- Adds new unique constraint (patient_id, scale_code, point_type)
"""

from alembic import op

revision = "20260302_01"
down_revision = "20260228_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE kdqol.measurement_points
            ADD COLUMN IF NOT EXISTS scale_code VARCHAR(20) NOT NULL DEFAULT 'KDQOL_SF';
    """)

    # Заменяем старый уникальный ключ (patient_id, point_type) → (patient_id, scale_code, point_type)
    op.execute("""
        ALTER TABLE kdqol.measurement_points
            DROP CONSTRAINT IF EXISTS uq_mp_patient_point_type;
    """)

    op.execute("""
        ALTER TABLE kdqol.measurement_points
            ADD CONSTRAINT uq_mp_patient_scale_point
                UNIQUE (patient_id, scale_code, point_type);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE kdqol.measurement_points
            DROP CONSTRAINT IF EXISTS uq_mp_patient_scale_point;
    """)

    op.execute("""
        ALTER TABLE kdqol.measurement_points
            ADD CONSTRAINT uq_mp_patient_point_type
                UNIQUE (patient_id, point_type);
    """)

    op.execute("""
        ALTER TABLE kdqol.measurement_points
            DROP COLUMN IF EXISTS scale_code;
    """)
