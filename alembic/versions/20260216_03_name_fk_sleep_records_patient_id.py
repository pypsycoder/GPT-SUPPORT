"""name fk sleep records patient id

Revision ID: 20260216_03
Revises: 20260216_02
Create Date: 2026-02-16 17:37:56.188705

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260216_03'
down_revision: Union[str, Sequence[str], None] = '20260216_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Убираем любой FK на patient_id (с именем или без) и создаём именованный с CASCADE
    op.execute("""
        DO $$
        DECLARE
            fk_name text;
        BEGIN
            -- удаляем все FK на patient_id кроме целевого
            FOR fk_name IN
                SELECT tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'sleep'
                  AND tc.table_name = 'sleep_records'
                  AND kcu.column_name = 'patient_id'
            LOOP
                EXECUTE format(
                    'ALTER TABLE sleep.sleep_records DROP CONSTRAINT %I', fk_name
                );
            END LOOP;
        END $$;
    """)
    op.create_foreign_key(
        'fk_sleep_records_patient_id',
        'sleep_records',
        'users',
        ['patient_id'],
        ['id'],
        source_schema='sleep',
        referent_schema='users',
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_sleep_records_patient_id',
        'sleep_records',
        schema='sleep',
        type_='foreignkey',
    )
    op.create_foreign_key(
        None,
        'sleep_records',
        'users',
        ['patient_id'],
        ['id'],
        source_schema='sleep',
        referent_schema='users',
    )
