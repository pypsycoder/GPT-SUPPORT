from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.agent import _build_system_prompt, generate_response
from app.llm.router import ModelTier, RequestType, RouterResult
from app.models.llm import LLMRequestLog


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


class FakeDB:
    def __init__(self) -> None:
        self.items: list[object] = []

    def add(self, item: object) -> None:
        self.items.append(item)

    async def flush(self) -> None:
        return None


async def test_generate_response_persists_pipeline_diagnostics(monkeypatch):
    fake_db = FakeDB()
    fake_client = SimpleNamespace(
        account_id="A1",
        call=AsyncMock(return_value=("Ответ ассистента", 120, 40, 850)),
    )
    fake_pool = SimpleNamespace(get_available=AsyncMock(return_value=fake_client))

    monkeypatch.setattr("app.llm.pool.pool", fake_pool)
    monkeypatch.setattr("app.llm.agent.pool", fake_pool)
    monkeypatch.setattr(
        "app.llm.context_builder.build_context_bundle",
        AsyncMock(
            return_value={
                "context": {
                    "recent_vitals": ["BP 120/80"],
                    "chat_history": [{"role": "assistant", "content": "Предыдущий ответ"}],
                    "rag_context": ["Relevant lesson chunk"],
                },
                "diagnostics": {
                    "patient_id": 42,
                    "query_length": 24,
                    "total_latency_ms": 17,
                    "sections_ok": ["recent_vitals", "chat_history"],
                    "sections_failed": ["sleep_summary"],
                    "section_latency_ms": {"recent_vitals": 3, "chat_history": 2},
                    "section_item_counts": {"recent_vitals": 1, "chat_history": 1},
                    "rag": {
                        "attempted": True,
                        "skipped_reason": None,
                        "hit_count": 1,
                        "error": None,
                        "latency_ms": 7,
                    },
                },
            }
        ),
    )
    monkeypatch.setattr(
        "app.llm.context_builder.format_context_for_llm",
        lambda ctx: "CTX\nRAG",
    )
    monkeypatch.setattr(
        "app.llm.parser.parse_patient_message",
        AsyncMock(return_value={"mood": "calm", "domain_hints": ["emotion"], "vitals": []}),
    )
    monkeypatch.setattr(
        "app.llm.agent._build_system_prompt",
        lambda domain, include_support_overlay=False: f"SYSTEM {domain}",
    )

    result = await generate_response(
        patient_id=42,
        user_input="Хочу понять, почему мне уже несколько дней тревожно",
        router_result=RouterResult(
            request_type=RequestType.SIMPLE,
            model_tier=ModelTier.PRO,
            domain_hint=None,
            priority=1,
        ),
        context={"daily_context": "DAILY"},
        db=fake_db,
    )

    diagnostics = result["diagnostics"]
    summary = diagnostics["summary"]

    assert diagnostics["classify"]["effective_domain"] == "emotion"
    assert diagnostics["parser"]["mood"] == "calm"
    assert diagnostics["prompt"]["rag_context_items"] == 1
    assert diagnostics["prompt"]["support_overlay_applied"] is True
    assert diagnostics["prompt"]["support_overlay_reasons"] == ["emotion_hint"]
    assert diagnostics["prompt"]["history_messages"] == 1
    assert diagnostics["llm_call"]["status"] == "ok"
    assert diagnostics["llm_call"]["tokens_input"] == 120
    assert diagnostics["llm_call"]["tokens_output"] == 40
    assert summary["status"] == "ok"
    assert "patient_context_sections" in summary["fallback_points"]
    assert summary["rag_hit"] is True
    assert summary["domain_effective"] == "emotion"

    log_item = next(item for item in fake_db.items if isinstance(item, LLMRequestLog))
    assert log_item.diagnostics_json == diagnostics


async def test_build_system_prompt_appends_support_overlay(monkeypatch):
    prompts = {
        "base_system.txt": "BASE",
        "domain_sleep.txt": "SLEEP",
        "policy_support_overlay.txt": "OVERLAY",
    }
    monkeypatch.setattr("app.llm.agent.load_prompt", lambda filename: prompts[filename])

    prompt = _build_system_prompt("sleep", include_support_overlay=True)

    assert prompt == "BASE\n\nSLEEP\n\nOVERLAY"


async def test_generate_response_applies_support_overlay_for_bad_mood(monkeypatch):
    fake_db = FakeDB()
    captured: dict[str, object] = {}

    async def fake_call(messages, system_prompt):
        captured["messages"] = messages
        captured["system_prompt"] = system_prompt
        return ("Поддерживающий ответ", 140, 44, 620)

    fake_client = SimpleNamespace(
        account_id="A1",
        call=AsyncMock(side_effect=fake_call),
    )
    fake_pool = SimpleNamespace(get_available=AsyncMock(return_value=fake_client))

    monkeypatch.setattr("app.llm.pool.pool", fake_pool)
    monkeypatch.setattr("app.llm.agent.pool", fake_pool)
    monkeypatch.setattr(
        "app.llm.context_builder.build_context_bundle",
        AsyncMock(
            return_value={
                "context": {
                    "sleep_summary": ["Плохо спал"],
                    "chat_history": [],
                    "rag_context": [],
                },
                "diagnostics": {
                    "patient_id": 7,
                    "query_length": 54,
                    "total_latency_ms": 11,
                    "sections_ok": ["sleep_summary"],
                    "sections_failed": [],
                    "section_latency_ms": {"sleep_summary": 3},
                    "section_item_counts": {"sleep_summary": 1},
                    "rag": {
                        "attempted": False,
                        "skipped_reason": "empty_query",
                        "hit_count": 0,
                        "error": None,
                        "latency_ms": 0,
                    },
                },
            }
        ),
    )
    monkeypatch.setattr(
        "app.llm.context_builder.format_context_for_llm",
        lambda ctx: "CTX",
    )
    monkeypatch.setattr(
        "app.llm.parser.parse_patient_message",
        AsyncMock(return_value={"mood": "bad", "domain_hints": ["sleep", "emotion"], "vitals": []}),
    )
    prompts = {
        "base_system.txt": "BASE",
        "domain_sleep.txt": "SLEEP",
        "policy_support_overlay.txt": "OVERLAY",
    }
    monkeypatch.setattr("app.llm.agent.load_prompt", lambda filename: prompts[filename])

    result = await generate_response(
        patient_id=7,
        user_input="Последние дни плохо сплю и тревожусь перед диализом",
        router_result=RouterResult(
            request_type=RequestType.SIMPLE,
            model_tier=ModelTier.PRO,
            domain_hint="sleep",
            priority=1,
        ),
        context={},
        db=fake_db,
    )

    diagnostics = result["diagnostics"]

    assert diagnostics["prompt"]["support_overlay_applied"] is True
    assert diagnostics["prompt"]["support_overlay_reasons"] == ["mood_bad", "emotion_hint"]
    assert "OVERLAY" in captured["system_prompt"]
