"""Basic smoke-tests for database migrations."""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_tables_exist_after_migration(async_session):
    """Ensure key tables are present after running Alembic migrations."""

    expected_tables = [
        "users.users",
        "scales.responses",
        "vitals.bp_measurement",
        "vitals.fluid_intake_event",
        "vitals.weight_measurement",
    ]

    for table in expected_tables:
        result = await async_session.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table})
        assert result.scalar() is not None, f"table {table} is missing after migrations"
