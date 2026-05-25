from pathlib import Path
import os

import pytest
import pytest_asyncio

from app.core.config import load_environment


os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
load_environment()

from core.db.engine import async_session_maker


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: tests that use the configured database or app wiring")
    config.addinivalue_line("markers", "unit: fast isolated tests")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = Path(str(item.fspath)).as_posix()
        node_id = item.nodeid

        if "tests_py/test_migrations.py" in path:
            item.add_marker(pytest.mark.integration)
            continue

        if (
            "tests_py/auth/" in path
            or "tests_py/bot/" in path
            or "tests_py/llm/" in path
            or "tests_py/vitals/" in path
        ):
            item.add_marker(pytest.mark.unit)
            continue

        if "tests_py/dialysis/test_dialysis.py" in path and "test_is_dialysis_day_" in node_id:
            item.add_marker(pytest.mark.unit)
            continue

        item.add_marker(pytest.mark.integration)


@pytest_asyncio.fixture
async def async_session():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()
