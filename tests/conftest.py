import asyncio
import inspect
from typing import Any

import pytest
import pytest_asyncio

from core.db.engine import async_session_maker


def pytest_pyfunc_call(pyfuncitem: Any) -> bool | None:
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(pyfuncitem.obj(**pyfuncitem.funcargs))
        finally:
            loop.close()
            asyncio.set_event_loop(None)
        return True
    return None


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: mark test as asyncio")


@pytest_asyncio.fixture
async def async_session():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()
