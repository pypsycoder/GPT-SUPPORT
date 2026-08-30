"""Простой in-process рейт-лимит на дорогие LLM-эндпоинты.

Деплой — один инстанс uvicorn (зафиксировано), поэтому счётчик в памяти
достаточен. Скользящее окно на пациента: не человек упрётся в лимит, а
разогнавшийся скрипт или злоупотребление.

Порог: ``CHAT_RATE_LIMIT_MAX`` запросов за ``CHAT_RATE_LIMIT_WINDOW_SEC`` секунд
(по умолчанию 20 / 60). ``0`` в ``MAX`` — лимит выключен.
"""

from __future__ import annotations

import os
import time
from collections import deque

from fastapi import HTTPException, status


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


_MAX = _int_env("CHAT_RATE_LIMIT_MAX", 20)
_WINDOW_SEC = float(_int_env("CHAT_RATE_LIMIT_WINDOW_SEC", 60))

# patient_id -> метки времени (monotonic) последних запросов в окне.
_hits: dict[int, deque[float]] = {}


def check(patient_id: int, *, now: float | None = None) -> None:
    """Учесть запрос пациента. ``HTTPException(429)`` при превышении окна."""
    if _MAX <= 0:
        return

    now = time.monotonic() if now is None else now
    cutoff = now - _WINDOW_SEC

    dq = _hits.setdefault(patient_id, deque())
    while dq and dq[0] < cutoff:
        dq.popleft()

    if len(dq) >= _MAX:
        retry_after = max(1, int(dq[0] + _WINDOW_SEC - now) + 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много сообщений подряд. Немного подожди и продолжим.",
            headers={"Retry-After": str(retry_after)},
        )

    dq.append(now)
    if not dq:
        _hits.pop(patient_id, None)


def reset() -> None:
    """Сбросить счётчики (для тестов)."""
    _hits.clear()
