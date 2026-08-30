from __future__ import annotations

import httpx
import pytest

from app.llm.errors import LLMResponseError, LLMTransportError
from app.llm.http import _backoff_seconds, request_json_with_policy, should_retry_http_status


pytestmark = [pytest.mark.unit]


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        self.calls += 1
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


@pytest.mark.asyncio
async def test_request_json_with_policy_retries_retryable_status(monkeypatch):
    request = httpx.Request("POST", "https://example.test/chat")
    fake_client = FakeClient(
        [
            httpx.Response(503, request=request, json={"error": "temporary"}),
            httpx.Response(200, request=request, json={"ok": True}),
        ]
    )

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.llm.http.get_shared_http_client", lambda _: fake_client)
    monkeypatch.setattr("app.llm.http.asyncio.sleep", fake_sleep)

    payload = await request_json_with_policy(
        "chat",
        method="POST",
        url="https://example.test/chat",
        operation="chat completion",
    )

    assert payload == {"ok": True}
    assert fake_client.calls == 2


@pytest.mark.asyncio
async def test_request_json_with_policy_raises_on_invalid_json(monkeypatch):
    request = httpx.Request("POST", "https://example.test/chat")
    fake_client = FakeClient(
        [
            httpx.Response(200, request=request, content=b"not-json", headers={"Content-Type": "application/json"}),
        ]
    )

    monkeypatch.setattr("app.llm.http.get_shared_http_client", lambda _: fake_client)

    with pytest.raises(LLMResponseError, match="invalid JSON payload"):
        await request_json_with_policy(
            "chat",
            method="POST",
            url="https://example.test/chat",
            operation="chat completion",
        )

    assert fake_client.calls == 1


@pytest.mark.asyncio
async def test_request_json_with_policy_wraps_timeout(monkeypatch):
    request = httpx.Request("POST", "https://example.test/chat")
    fake_client = FakeClient([httpx.ReadTimeout("timed out", request=request)])

    monkeypatch.setattr("app.llm.http.get_shared_http_client", lambda _: fake_client)

    with pytest.raises(LLMTransportError, match="timeout"):
        await request_json_with_policy(
            "oauth",
            method="POST",
            url="https://example.test/oauth",
            operation="oauth",
            retry_count=0,
        )


def test_should_retry_http_status_matches_retry_policy():
    assert should_retry_http_status(429) is True
    assert should_retry_http_status(503) is True
    assert should_retry_http_status(400) is False


def _resp(status: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status, request=httpx.Request("POST", "https://x.test"), headers=headers or {}
    )


def test_backoff_429_is_exponential_and_capped():
    b1 = _backoff_seconds(429, 1, _resp(429))
    b2 = _backoff_seconds(429, 2, _resp(429))
    b9 = _backoff_seconds(429, 9, _resp(429))
    assert b1 == 2.0
    assert b2 == 4.0
    assert b9 == 8.0  # capped at _MAX_BACKOFF_SEC


def test_backoff_429_respects_retry_after_header():
    assert _backoff_seconds(429, 1, _resp(429, {"Retry-After": "5"})) == 5.0
    # но не выше потолка
    assert _backoff_seconds(429, 1, _resp(429, {"Retry-After": "999"})) == 8.0


def test_backoff_non_429_stays_fast():
    assert _backoff_seconds(503, 3, _resp(503)) == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_chat_retries_429_twice_then_succeeds(monkeypatch):
    request = httpx.Request("POST", "https://example.test/chat")
    fake_client = FakeClient(
        [
            httpx.Response(429, request=request, json={"error": "rate"}),
            httpx.Response(429, request=request, json={"error": "rate"}),
            httpx.Response(200, request=request, json={"ok": True}),
        ]
    )
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.llm.http.get_shared_http_client", lambda _: fake_client)
    monkeypatch.setattr("app.llm.http.asyncio.sleep", fake_sleep)

    payload = await request_json_with_policy(
        "chat", method="POST", url="https://example.test/chat", operation="chat completion",
    )

    assert payload == {"ok": True}
    assert fake_client.calls == 3           # 1 + 2 retries (chat retry_count=2)
    assert slept == [2.0, 4.0]              # backed off between attempts
