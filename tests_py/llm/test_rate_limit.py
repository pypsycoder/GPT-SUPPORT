"""In-process рейт-лимит на /api/chat/message."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.llm import rate_limit


pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clean():
    rate_limit.reset()
    yield
    rate_limit.reset()


def test_allows_up_to_the_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "_MAX", 3)
    monkeypatch.setattr(rate_limit, "_WINDOW_SEC", 60.0)

    for i in range(3):
        rate_limit.check(1, now=100.0 + i)  # не должно бросить


def test_blocks_over_the_limit_with_retry_after(monkeypatch):
    monkeypatch.setattr(rate_limit, "_MAX", 3)
    monkeypatch.setattr(rate_limit, "_WINDOW_SEC", 60.0)

    for i in range(3):
        rate_limit.check(1, now=100.0 + i)

    with pytest.raises(HTTPException) as exc:
        rate_limit.check(1, now=103.0)

    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) >= 1


def test_window_slides(monkeypatch):
    monkeypatch.setattr(rate_limit, "_MAX", 2)
    monkeypatch.setattr(rate_limit, "_WINDOW_SEC", 10.0)

    rate_limit.check(1, now=0.0)
    rate_limit.check(1, now=1.0)
    # старые метки вышли из окна — снова можно
    rate_limit.check(1, now=12.0)


def test_per_patient_isolation(monkeypatch):
    monkeypatch.setattr(rate_limit, "_MAX", 1)
    monkeypatch.setattr(rate_limit, "_WINDOW_SEC", 60.0)

    rate_limit.check(1, now=0.0)
    rate_limit.check(2, now=0.0)  # другой пациент — свой счётчик
    with pytest.raises(HTTPException):
        rate_limit.check(1, now=0.5)


def test_disabled_when_max_zero(monkeypatch):
    monkeypatch.setattr(rate_limit, "_MAX", 0)
    for i in range(100):
        rate_limit.check(1, now=float(i))
