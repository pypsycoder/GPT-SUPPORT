from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import load_environment


load_environment()

from app.core.config import settings
from app.llm.scheduler import start_scheduler, stop_scheduler
from core.db.engine import engine


logger = logging.getLogger("gpt-support-llm.worker")
_scheduler_lock_conn: AsyncConnection | None = None


async def acquire_scheduler_lock() -> bool:
    global _scheduler_lock_conn

    if _scheduler_lock_conn is not None:
        return True

    conn = await engine.connect()
    result = await conn.execute(
        text("SELECT pg_try_advisory_lock(:lock_id)"),
        {"lock_id": settings.scheduler_lock_id},
    )
    has_lock = bool(result.scalar())
    if not has_lock:
        await conn.close()
        return False

    _scheduler_lock_conn = conn
    return True


async def release_scheduler_lock() -> None:
    global _scheduler_lock_conn

    if _scheduler_lock_conn is None:
        return

    try:
        await _scheduler_lock_conn.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": settings.scheduler_lock_id},
        )
    finally:
        await _scheduler_lock_conn.close()
        _scheduler_lock_conn = None


async def run_worker() -> None:
    if not settings.scheduler_enabled:
        raise RuntimeError("SCHEDULER_ENABLED=true is required to run the scheduler worker")

    has_lock = await acquire_scheduler_lock()
    if not has_lock:
        logger.warning("scheduler worker is already active in another instance")
        return

    start_scheduler()
    logger.info("scheduler worker started")

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        stop_scheduler()
        await release_scheduler_lock()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
