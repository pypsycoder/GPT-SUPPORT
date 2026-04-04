from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.llm import context_builder
from app.llm.errors import RetrievalError


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


async def test_build_context_bundle_collects_section_and_rag_diagnostics(monkeypatch):
    monkeypatch.setattr(
        context_builder,
        "_get_recent_vitals",
        AsyncMock(return_value=["BP 120/80"]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_medication_adherence",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_sleep_summary",
        AsyncMock(side_effect=RuntimeError("sleep source unavailable")),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_active_practices",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_last_scale_scores",
        AsyncMock(return_value=["HADS: 7"]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_recent_weight",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_recent_water",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_routine_summary",
        AsyncMock(return_value=["Routine: 4 of 7"]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_practices_summary",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_chat_history",
        AsyncMock(return_value=[{"role": "user", "content": "hi"}]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_rag_context",
        AsyncMock(
            return_value=(
                ["Relevant lesson chunk"],
                {
                    "backend": "python_cosine",
                    "backend_selected": "python_cosine",
                    "candidate_rows": 10,
                    "query_vector_dims": 1024,
                    "embedding_request_ms": 120,
                    "vector_search_ms": 45,
                    "progress_lookup_ms": 3,
                    "pgvector_extension_installed": False,
                    "pgvector_column_present": False,
                    "pgvector_index_present": False,
                    "pgvector_blocker": "pgvector_extension_missing",
                    "invalid_embedding_rows": 0,
                },
            )
        ),
    )

    bundle = await context_builder.build_context_bundle(
        patient_id=42,
        db=object(),
        query="long enough query for retrieval",
    )

    context = bundle["context"]
    diagnostics = bundle["diagnostics"]

    assert context["recent_vitals"] == ["BP 120/80"]
    assert context["sleep_summary"] == []
    assert context["rag_context"] == ["Relevant lesson chunk"]

    assert "recent_vitals" in diagnostics["sections_ok"]
    assert "sleep_summary" in diagnostics["sections_failed"]
    assert diagnostics["section_latency_ms"]["recent_vitals"] >= 0
    assert diagnostics["section_item_counts"]["recent_vitals"] == 1
    assert diagnostics["total_latency_ms"] >= 0
    assert diagnostics["rag"]["attempted"] is True
    assert diagnostics["rag"]["hit_count"] == 1
    assert diagnostics["rag"]["error"] is None
    assert diagnostics["rag"]["backend"] == "python_cosine"
    assert diagnostics["rag"]["pgvector_blocker"] == "pgvector_extension_missing"
    assert diagnostics["rag"]["embedding_request_ms"] == 120
    assert diagnostics["rag"]["vector_search_ms"] == 45
    assert diagnostics["rag"]["progress_lookup_ms"] == 3


async def test_build_context_bundle_records_retrieval_error(monkeypatch):
    monkeypatch.setattr(context_builder, "_get_recent_vitals", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_medication_adherence", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_sleep_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_active_practices", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_last_scale_scores", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_recent_weight", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_recent_water", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_routine_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_practices_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_chat_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        context_builder,
        "_get_rag_context",
        AsyncMock(side_effect=RetrievalError("embedding provider unavailable")),
    )

    bundle = await context_builder.build_context_bundle(
        patient_id=42,
        db=object(),
        query="long enough query for retrieval",
    )

    diagnostics = bundle["diagnostics"]
    assert diagnostics["rag"]["attempted"] is True
    assert diagnostics["rag"]["hit_count"] == 0
    assert diagnostics["rag"]["error"] == "embedding provider unavailable"


async def test_build_context_bundle_marks_short_query_rag_skip(monkeypatch):
    monkeypatch.setattr(context_builder, "_get_recent_vitals", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_medication_adherence", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_sleep_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_active_practices", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_last_scale_scores", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_recent_weight", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_recent_water", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_routine_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_practices_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_chat_history", AsyncMock(return_value=[]))
    rag_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(context_builder, "_get_rag_context", rag_mock)

    bundle = await context_builder.build_context_bundle(
        patient_id=42,
        db=object(),
        query="short query",
    )

    diagnostics = bundle["diagnostics"]
    assert diagnostics["rag"]["attempted"] is False
    assert diagnostics["rag"]["skipped_reason"] == "query_too_short"
    rag_mock.assert_not_called()
