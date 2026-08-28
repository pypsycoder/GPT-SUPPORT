"""Тесты ``ToolRegistry`` и инструмента ``search_education`` (шаг 7)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.llm import tools
from app.llm.errors import RetrievalError

pytestmark = [pytest.mark.unit]


# --------------------------------------------------------------------------- #
# ToolRegistry
# --------------------------------------------------------------------------- #

class _EchoArgs(BaseModel):
    text: str


class _EchoResult(BaseModel):
    text: str


def _fresh_registry() -> tools.ToolRegistry:
    registry = tools.ToolRegistry()

    @registry.register("echo", "Возвращает текст обратно.", _EchoArgs)
    async def _echo(args: _EchoArgs) -> _EchoResult:
        return _EchoResult(text=args.text)

    return registry


def test_specs_builds_json_schema_via_structured_module():
    registry = _fresh_registry()

    specs = registry.specs(["echo"])

    assert len(specs) == 1
    assert specs[0]["name"] == "echo"
    assert specs[0]["parameters"]["required"] == ["text"]
    assert specs[0]["parameters"]["additionalProperties"] is False


def test_specs_filters_by_name_when_names_given():
    registry = _fresh_registry()

    assert registry.specs(["unknown"]) == []
    assert registry.specs(None) == registry.specs()


@pytest.mark.asyncio
async def test_invoke_returns_model_result_as_json():
    registry = _fresh_registry()

    result = await registry.invoke("echo", {"text": "привет"})

    assert result == '{"text":"привет"}' or "привет" in result  # BaseModel.model_dump_json() формат


@pytest.mark.asyncio
async def test_invoke_unknown_tool_returns_error_json_not_raise():
    registry = _fresh_registry()

    result = await registry.invoke("nonexistent", {})

    assert "unknown_tool:nonexistent" in result


@pytest.mark.asyncio
async def test_invoke_invalid_arguments_returns_error_json_not_raise():
    registry = _fresh_registry()

    result = await registry.invoke("echo", {"wrong_field": 1})

    assert "invalid_arguments" in result


@pytest.mark.asyncio
async def test_invoke_handler_exception_returns_error_json_not_raise():
    registry = tools.ToolRegistry()

    @registry.register("boom", "Падает специально.", _EchoArgs)
    async def _boom(args: _EchoArgs) -> _EchoResult:
        raise RuntimeError("что-то пошло не так")

    result = await registry.invoke("boom", {"text": "x"})

    assert "tool_failed" in result


@pytest.mark.asyncio
async def test_invoke_passes_only_kwargs_present_in_handler_signature():
    registry = tools.ToolRegistry()
    seen: dict = {}

    @registry.register("needs_db", "Хендлер, которому нужен db, но не patient_id.", _EchoArgs)
    async def _needs_db(args: _EchoArgs, *, db) -> _EchoResult:
        seen["db"] = db
        return _EchoResult(text=args.text)

    await registry.invoke("needs_db", {"text": "x"}, db="the-db", patient_id=42)

    assert seen["db"] == "the-db"


# --------------------------------------------------------------------------- #
# search_education
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_search_education_happy_path(monkeypatch):
    fake_retrieve = AsyncMock(
        return_value={
            "modules": [
                {"title": "Урок о диете", "chunk": "Много текста " * 50},
                {"title": "Урок о сне", "chunk": "Коротко"},
            ],
        }
    )
    monkeypatch.setattr("app.rag.retriever.retrieve_relevant_modules_with_meta", fake_retrieve)

    result = await tools.registry.invoke(
        "search_education", {"query": "можно ли есть картошку"}, patient_id=7, db=object()
    )

    assert "Урок о диете" in result
    assert "Урок о сне" in result
    fake_retrieve.assert_awaited_once()
    args, kwargs = fake_retrieve.call_args
    assert args[0] == "можно ли есть картошку"
    assert args[1] == 7


@pytest.mark.asyncio
async def test_search_education_retrieval_error_becomes_tool_error_not_raise(monkeypatch):
    monkeypatch.setattr(
        "app.rag.retriever.retrieve_relevant_modules_with_meta",
        AsyncMock(side_effect=RetrievalError("embeddings down")),
    )

    result = await tools.registry.invoke(
        "search_education", {"query": "что-нибудь"}, patient_id=7, db=object()
    )

    assert "tool_failed" in result
