"""vitals: add measurements table

Revision ID: 980f6beb1f52
Revises:
Create Date: 2025-11-12 16:01:38.803048
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "980f6beb1f52"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) гарантируем наличие схем проекта
    op.execute('CREATE SCHEMA IF NOT EXISTS "users"')
    op.execute('CREATE SCHEMA IF NOT EXISTS "scales"')
    op.execute('CREATE SCHEMA IF NOT EXISTS "vitals"')

    # 2) таблица vitals.measurements
    op.create_table(
        "measurements",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("bp_sys", sa.Integer(), nullable=True),
        sa.Column("bp_dia", sa.Integer(), nullable=True),
        sa.Column("pulse", sa.Integer(), nullable=True),
        sa.Column("fluid_intake", sa.Numeric(), nullable=True),
        sa.Column(
            "measured_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.users.id"]),
        schema="vitals",
    )

    # 3) правки таблицы users.users — ВАЖНО: указываем schema="users"
    op.add_column("users", sa.Column("external_ids", sa.JSON(), nullable=True), schema="users")
    op.alter_column("users", "full_name", existing_type=sa.VARCHAR(), nullable=True, schema="users")
    op.alter_column("users", "consent_personal_data", existing_type=sa.BOOLEAN(), nullable=False, schema="users")
    op.alter_column("users", "consent_bot_use", existing_type=sa.BOOLEAN(), nullable=False, schema="users")
    op.alter_column("users", "telegram_id", existing_type=sa.VARCHAR(), nullable=False, schema="users")

    # если у тебя раньше был индекс в users.users — можно восстановить при желании:
    # op.create_index(op.f('ix_users_users_id'), 'users', ['id'], unique=False, schema='users')

    # 4) FK в scales.*
    op.drop_constraint(op.f("drafts_user_id_fkey"), "drafts", schema="scales", type_="foreignkey")
    op.create_foreign_key(
        None, "drafts", "users", ["user_id"], ["id"], source_schema="scales", referent_schema="users"
    )

    op.drop_constraint(op.f("responses_user_id_fkey"), "responses", schema="scales", type_="foreignkey")
    op.create_foreign_key(
        None, "responses", "users", ["user_id"], ["id"], source_schema="scales", referent_schema="users"
    )

    # НИЧЕГО не делаем с public.alembic_version — это служебная таблица Alembic.


def downgrade() -> None:
    # откатываем в обратном порядке

    # 1) связи в scales.*
    op.drop_constraint(None, "responses", schema="scales", type_="foreignkey")
    op.create_foreign_key(
        op.f("responses_user_id_fkey"), "responses", "users", ["user_id"], ["id"], source_schema="scales", referent_schema="users"
    )

    op.drop_constraint(None, "drafts", schema="scales", type_="foreignkey")
    op.create_foreign_key(
        op.f("drafts_user_id_fkey"), "drafts", "users", ["user_id"], ["id"], source_schema="scales", referent_schema="users"
    )

    # 2) откат правок users.users
    # op.drop_index(op.f('ix_users_users_id'), table_name='users', schema='users')  # если создавали в upgrade
    op.alter_column("users", "telegram_id", existing_type=sa.VARCHAR(), nullable=True, schema="users")
    op.alter_column("users", "consent_bot_use", existing_type=sa.BOOLEAN(), nullable=True, schema="users")
    op.alter_column("users", "consent_personal_data", existing_type=sa.BOOLEAN(), nullable=True, schema="users")
    op.alter_column("users", "full_name", existing_type=sa.VARCHAR(), nullable=False, schema="users")
    op.drop_column("users", "external_ids", schema="users")

    # 3) дроп таблицы vitals.measurements
    op.drop_table("measurements", schema="vitals")

    # схемы сознательно не трогаем в откате
