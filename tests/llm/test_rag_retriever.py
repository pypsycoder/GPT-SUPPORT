from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.rag import retriever


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class FakeDB:
    def __init__(self, query_rows, progress_rows):
        self._query_rows = query_rows
        self._progress_rows = progress_rows
        self.calls = 0

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return FakeResult(self._query_rows)
        return FakeResult(self._progress_rows)


async def test_retrieve_relevant_modules_with_meta_reports_python_backend(monkeypatch):
    query_rows = [
        SimpleNamespace(
            lesson_id=10,
            chunk_text="Chunk 1",
            card_index=1,
            embedding=json.dumps([1.0, 0.0]),
            lesson_title="Lesson 1",
        ),
        SimpleNamespace(
            lesson_id=20,
            chunk_text="Chunk 2",
            card_index=1,
            embedding=json.dumps([0.5, 0.5]),
            lesson_title="Lesson 2",
        ),
    ]
    db = FakeDB(query_rows=query_rows, progress_rows=[(10,)])

    monkeypatch.setattr(retriever, "_get_query_embedding", AsyncMock(return_value=[1.0, 0.0]))
    monkeypatch.setattr(
        retriever,
        "get_rag_backend_info",
        AsyncMock(
            return_value={
                "backend": "python_cosine",
                "extension_installed": False,
                "vector_column_present": False,
                "vector_index_present": False,
                "blocker": "pgvector_extension_missing",
            }
        ),
    )

    result = await retriever.retrieve_relevant_modules_with_meta(
        query="help me",
        patient_id=7,
        db=db,
        top_k=2,
    )

    assert result["meta"]["backend"] == "python_cosine"
    assert result["meta"]["backend_selected"] == "python_cosine"
    assert result["meta"]["pgvector_blocker"] == "pgvector_extension_missing"
    assert result["meta"]["query_vector_dims"] == 2
    assert result["meta"]["candidate_rows"] == 2
    assert result["meta"]["embedding_request_ms"] >= 0
    assert result["meta"]["vector_search_ms"] >= 0
    assert result["meta"]["progress_lookup_ms"] >= 0
    assert len(result["modules"]) == 2
    assert result["modules"][0]["lesson_id"] == 10
    assert result["modules"][0]["is_read"] is True
    assert result["modules"][1]["is_read"] is False


async def test_retrieve_relevant_modules_with_meta_reports_pgvector_backend(monkeypatch):
    query_rows = [
        SimpleNamespace(
            lesson_id=30,
            chunk_text="Chunk 30",
            card_index=1,
            lesson_title="Lesson 30",
            similarity=0.91,
        ),
        SimpleNamespace(
            lesson_id=30,
            chunk_text="Chunk 30 duplicate",
            card_index=2,
            lesson_title="Lesson 30",
            similarity=0.89,
        ),
        SimpleNamespace(
            lesson_id=40,
            chunk_text="Chunk 40",
            card_index=1,
            lesson_title="Lesson 40",
            similarity=0.77,
        ),
    ]
    db = FakeDB(query_rows=query_rows, progress_rows=[(40,)])

    monkeypatch.setattr(retriever, "_get_query_embedding", AsyncMock(return_value=[1.0, 0.0, 0.5]))
    monkeypatch.setattr(
        retriever,
        "get_rag_backend_info",
        AsyncMock(
            return_value={
                "backend": "pgvector",
                "extension_installed": True,
                "vector_column_present": True,
                "vector_index_present": True,
                "blocker": None,
            }
        ),
    )

    result = await retriever.retrieve_relevant_modules_with_meta(
        query="help me",
        patient_id=7,
        db=db,
        top_k=2,
    )

    assert result["meta"]["backend"] == "pgvector"
    assert result["meta"]["backend_selected"] == "pgvector"
    assert result["meta"]["pgvector_blocker"] is None
    assert result["meta"]["query_vector_dims"] == 3
    assert result["meta"]["candidate_rows"] == 3
    assert result["meta"]["embedding_request_ms"] >= 0
    assert result["meta"]["vector_search_ms"] >= 0
    assert result["meta"]["progress_lookup_ms"] >= 0
    assert len(result["modules"]) == 2
    assert result["modules"][0]["lesson_id"] == 30
    assert result["modules"][0]["is_read"] is False
    assert result["modules"][1]["lesson_id"] == 40
    assert result["modules"][1]["is_read"] is True
