"""Отдельный процесс-планировщик (запасной путь).

В проде на одном инстансе uvicorn планировщик стартует в lifespan
``app/main.py`` за флагом ``SCHEDULER_ENABLED``. Этот модуль оставлен как
запасной путь для деплоя, где API и планировщик разнесены по процессам:

    python -m app.llm.worker

Advisory-lock и функции старта/остановки — общие с lifespan
(``app.llm.scheduler``), поэтому два пути никогда не поднимут планировщик дважды.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import load_environment


load_environment()

from app.core.config import settings
from app.llm.scheduler import (
    acquire_scheduler_lock,
    release_scheduler_lock,
    start_scheduler,
    stop_scheduler,
)
from core.db.engine import engine


logger = logging.getLogger("gpt-support-llm.worker")


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
