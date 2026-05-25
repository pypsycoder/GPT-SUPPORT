from __future__ import annotations

import httpx
import pytest

from app.llm.errors import LLMResponseError, LLMTransportError
from app.llm.http import request_json_with_policy, should_retry_http_status


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
