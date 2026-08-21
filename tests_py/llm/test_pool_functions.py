"""Тесты ``GigaChatClient.call_with_functions()`` (шаг 7) и regression-проверка
рефакторенного ``call()`` — их общая обвязка (``_execute``) не должна была
поменять поведение ``call()``, только вынести retry/telemetry в отдельный метод.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.llm.errors import LLMTransportError
from app.llm.pool import FunctionCall, FunctionCallResult, GigaChatClient, _SharedAccountState

pytestmark = [pytest.mark.unit]


def _client() -> GigaChatClient:
    client = GigaChatClient("A1", "key", "pro", shared_state=_SharedAccountState(api_key="key"))
    return client


def _patch_token(monkeypatch, client: GigaChatClient) -> None:
    monkeypatch.setattr(client, "_get_access_token", AsyncMock(return_value="tok"))


def _response(message: dict, *, usage: dict | None = None, finish_reason: str = "stop") -> dict:
    return {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.mark.asyncio
async def test_call_with_functions_parses_dict_arguments(monkeypatch):
    client = _client()
    _patch_token(monkeypatch, client)
    monkeypatch.setattr(
        "app.llm.pool.request_json_with_policy",
        AsyncMock(
            return_value=_response(
                {
                    "content": "",
                    "function_call": {"name": "search_education", "arguments": {"query": "диета"}},
                    "functions_state_id": "fsid-1",
                }
            )
        ),
    )

    result = await client.call_with_functions(
        [{"role": "user", "content": "привет"}],
        "system",
        functions=[{"name": "search_education", "description": "...", "parameters": {}}],
    )

    assert isinstance(result, FunctionCallResult)
    assert result.function_call == FunctionCall(name="search_education", arguments={"query": "диета"})
    assert result.functions_state_id == "fsid-1"
    assert result.tokens_in == 10
    assert result.tokens_out == 5


@pytest.mark.asyncio
async def test_call_with_functions_parses_json_string_arguments(monkeypatch):
    client = _client()
    _patch_token(monkeypatch, client)
    monkeypatch.setattr(
        "app.llm.pool.request_json_with_policy",
        AsyncMock(
            return_value=_response(
                {
                    "content": "",
                    "function_call": {"name": "search_education", "arguments": '{"query": "диета"}'},
                }
            )
        ),
    )

    result = await client.call_with_functions(
        [{"role": "user", "content": "привет"}],
        "system",
        functions=[{"name": "search_education", "description": "...", "parameters": {}}],
    )

    assert result.function_call == FunctionCall(name="search_education", arguments={"query": "диета"})
    assert result.functions_state_id is None


@pytest.mark.asyncio
async def test_call_with_functions_no_function_call_returns_none(monkeypatch):
    client = _client()
    _patch_token(monkeypatch, client)
    monkeypatch.setattr(
        "app.llm.pool.request_json_with_policy",
        AsyncMock(return_value=_response({"content": "просто ответ"})),
    )

    result = await client.call_with_functions(
        [{"role": "user", "content": "привет"}],
        "system",
        functions=[{"name": "search_education", "description": "...", "parameters": {}}],
    )

    assert result.function_call is None
    assert result.content == "просто ответ"


@pytest.mark.asyncio
async def test_call_with_functions_sends_functions_not_response_format(monkeypatch):
    client = _client()
    _patch_token(monkeypatch, client)
    fake_post = AsyncMock(return_value=_response({"content": "ok"}))
    monkeypatch.setattr("app.llm.pool.request_json_with_policy", fake_post)

    await client.call_with_functions(
        [{"role": "user", "content": "привет"}],
        "system",
        functions=[{"name": "search_education", "description": "...", "parameters": {}}],
        function_call="auto",
    )

    payload = fake_post.call_args.kwargs["json_body"]
    assert payload["functions"] == [{"name": "search_education", "description": "...", "parameters": {}}]
    assert payload["function_call"] == "auto"
    assert "response_format" not in payload


@pytest.mark.asyncio
async def test_call_still_returns_text_tuple_after_refactor(monkeypatch):
    """Regression: call() внешне не изменился после выноса _execute()."""
    client = _client()
    _patch_token(monkeypatch, client)
    monkeypatch.setattr(
        "app.llm.pool.request_json_with_policy",
        AsyncMock(return_value=_response({"content": "текст ответа"})),
    )

    text, tokens_in, tokens_out, latency_ms = await client.call(
        [{"role": "user", "content": "привет"}], "system"
    )

    assert text == "текст ответа"
    assert tokens_in == 10
    assert tokens_out == 5
    assert latency_ms >= 0


@pytest.mark.asyncio
async def test_call_retries_once_on_transport_error_then_succeeds(monkeypatch):
    client = _client()
    _patch_token(monkeypatch, client)
    fake_post = AsyncMock(
        side_effect=[LLMTransportError("boom"), _response({"content": "ok after retry"})]
    )
    monkeypatch.setattr("app.llm.pool.request_json_with_policy", fake_post)

    text, *_ = await client.call([{"role": "user", "content": "привет"}], "system")

    assert text == "ok after retry"
    assert fake_post.await_count == 2


@pytest.mark.asyncio
async def test_call_raises_after_second_failure(monkeypatch):
    client = _client()
    _patch_token(monkeypatch, client)
    monkeypatch.setattr(
        "app.llm.pool.request_json_with_policy",
        AsyncMock(side_effect=LLMTransportError("boom")),
    )

    with pytest.raises(LLMTransportError):
        await client.call([{"role": "user", "content": "привет"}], "system")
