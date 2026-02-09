"""Remove patient_token: education tables use user_id, users table drops patient_token.

Revision ID: a1b2c3d4e5f6
Revises: 5e1f8a2c3b4d
Create Date: 2026-02-08

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5e1f8a2c3b4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) education.lesson_progress: add user_id, backfill, drop patient_token
    op.add_column(
        'lesson_progress',
        sa.Column('user_id', sa.Integer(), nullable=True),
        schema='education',
    )
    op.execute(sa.text("""
        UPDATE education.lesson_progress p
        SET user_id = u.id
        FROM users.users u
        WHERE u.patient_token = p.patient_token
    """))
    op.execute(sa.text("DELETE FROM education.lesson_progress WHERE user_id IS NULL"))
    op.alter_column(
        'lesson_progress',
        'user_id',
        existing_type=sa.Integer(),
        nullable=False,
        schema='education',
    )
    op.create_foreign_key(
        'fk_lesson_progress_user_id',
        'lesson_progress', 'users',
        ['user_id'], ['id'],
        source_schema='education', referent_schema='users',
        ondelete='CASCADE',
    )
    op.create_index(
        op.f('ix_education_lesson_progress_user_id'),
        'lesson_progress', ['user_id'],
        schema='education',
    )
    op.drop_index(op.f('ix_education_lesson_progress_patient_token'), table_name='lesson_progress', schema='education')
    op.drop_column('lesson_progress', 'patient_token', schema='education')

    # 2) education.lesson_test_results: add user_id, backfill, drop patient_token
    op.add_column(
        'lesson_test_results',
        sa.Column('user_id', sa.Integer(), nullable=True),
        schema='education',
    )
    op.execute(sa.text("""
        UPDATE education.lesson_test_results r
        SET user_id = u.id
        FROM users.users u
        WHERE u.patient_token = r.patient_token
    """))
    op.execute(sa.text("DELETE FROM education.lesson_test_results WHERE user_id IS NULL"))
    op.alter_column(
        'lesson_test_results',
        'user_id',
        existing_type=sa.Integer(),
        nullable=False,
        schema='education',
    )
    op.create_foreign_key(
        'fk_lesson_test_results_user_id',
        'lesson_test_results', 'users',
        ['user_id'], ['id'],
        source_schema='education', referent_schema='users',
        ondelete='CASCADE',
    )
    op.create_index(
        op.f('ix_education_lesson_test_results_user_id'),
        'lesson_test_results', ['user_id'],
        schema='education',
    )
    op.drop_index(op.f('ix_education_lesson_test_results_patient_token'), table_name='lesson_test_results', schema='education')
    op.drop_column('lesson_test_results', 'patient_token', schema='education')

    # 3) users.users: drop patient_token
    op.drop_index(op.f('ix_users_users_patient_token'), table_name='users', schema='users')
    op.drop_column('users', 'patient_token', schema='users')


def downgrade() -> None:
    op.add_column(
        'users',
        sa.Column('patient_token', sa.String(length=64), nullable=True),
        schema='users',
    )
    op.create_index(op.f('ix_users_users_patient_token'), 'users', ['patient_token'], unique=True, schema='users')

    op.add_column(
        'lesson_progress',
        sa.Column('patient_token', sa.String(length=64), nullable=True),
        schema='education',
    )
    op.execute(sa.text("""
        UPDATE education.lesson_progress p
        SET patient_token = u.patient_token
        FROM users.users u
        WHERE u.id = p.user_id
    """))
    op.alter_column('lesson_progress', 'patient_token', nullable=False, schema='education')
    op.drop_constraint('fk_lesson_progress_user_id', 'lesson_progress', schema='education', type_='foreignkey')
    op.drop_index(op.f('ix_education_lesson_progress_user_id'), table_name='lesson_progress', schema='education')
    op.create_index(op.f('ix_education_lesson_progress_patient_token'), 'lesson_progress', ['patient_token'], schema='education')
    op.drop_column('lesson_progress', 'user_id', schema='education')

    op.add_column(
        'lesson_test_results',
        sa.Column('patient_token', sa.String(length=64), nullable=True),
        schema='education',
    )
    op.execute(sa.text("""
        UPDATE education.lesson_test_results r
        SET patient_token = u.patient_token
        FROM users.users u
        WHERE u.id = r.user_id
    """))
    op.alter_column('lesson_test_results', 'patient_token', nullable=False, schema='education')
    op.drop_constraint('fk_lesson_test_results_user_id', 'lesson_test_results', schema='education', type_='foreignkey')
    op.drop_index(op.f('ix_education_lesson_test_results_user_id'), table_name='lesson_test_results', schema='education')
    op.create_index(op.f('ix_education_lesson_test_results_patient_token'), 'lesson_test_results', ['patient_token'], schema='education')
    op.drop_column('lesson_test_results', 'user_id', schema='education')
