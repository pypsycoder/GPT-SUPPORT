"""
RAG Retriever - retrieves relevant educational chunks for the current query.

Embeddings are currently stored as JSON strings in TEXT columns.
Similarity is still computed in Python until pgvector migration.
"""

from __future__ import annotations

import json
import logging
import math
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.errors import LLMResponseError, LLMTransportError, RetrievalError
from app.llm.http import request_json_with_policy
from app.rag.capabilities import get_rag_backend_info


logger = logging.getLogger("rag.retriever")

EMBEDDINGS_URL = "https://gigachat.devices.sberbank.ru/api/v1/embeddings"


async def _get_query_embedding(query: str) -> list[float]:
    from app.llm.pool import pool

    gc_client = await pool.get_available("lite")
    token = await gc_client._get_access_token()

    try:
        data = await request_json_with_policy(
            "embeddings",
            method="POST",
            url=EMBEDDINGS_URL,
            operation="query embeddings",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json_body={"model": "Embeddings", "input": [query]},
        )
        return data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMResponseError("embeddings response payload is invalid") from exc


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _mark_read_progress(
    *,
    patient_id: int,
    db: AsyncSession,
    modules: list[dict],
) -> tuple[list[dict], int]:
    if not modules:
        return [], 0

    lesson_ids = [int(module["lesson_id"]) for module in modules]
    started = time.monotonic()
    progress_result = await db.execute(
        text(
            """
            SELECT lesson_id
            FROM education.lesson_progress
            WHERE user_id = :patient_id
              AND is_completed = true
              AND lesson_id = ANY(:lesson_ids)
            """
        ),
        {"patient_id": patient_id, "lesson_ids": lesson_ids},
    )
    read_ids: set[int] = {row[0] for row in progress_result.fetchall()}
    progress_lookup_ms = int((time.monotonic() - started) * 1000)

    for module in modules:
        module["is_read"] = int(module["lesson_id"]) in read_ids
    return modules, progress_lookup_ms


async def _retrieve_with_python_cosine(
    *,
    query_vec: list[float],
    patient_id: int,
    db: AsyncSession,
    top_k: int,
) -> dict[str, object]:
    rows_result = await db.execute(
        text(
            """
            SELECT le.lesson_id,
                   le.chunk_text,
                   le.card_index,
                   le.embedding,
                   l.title AS lesson_title
            FROM education.lesson_embeddings le
            JOIN education.lessons l ON l.id = le.lesson_id
            WHERE le.embedding IS NOT NULL
            """
        )
    )
    rows = rows_result.fetchall()

    if not rows:
        return {
            "modules": [],
            "meta": {
                "backend": "python_cosine",
                "candidate_rows": 0,
                "invalid_embedding_rows": 0,
            },
        }

    scored: list[tuple[float, object]] = []
    invalid_embedding_rows = 0
    for row in rows:
        try:
            emb = json.loads(row.embedding)
            sim = _cosine_similarity(query_vec, emb)
            scored.append((sim, row))
        except (json.JSONDecodeError, TypeError, ValueError):
            invalid_embedding_rows += 1

    if invalid_embedding_rows:
        logger.warning("[retriever] skipped %d malformed embedding rows", invalid_embedding_rows)

    scored.sort(key=lambda x: x[0], reverse=True)

    seen: dict[int, tuple[float, object]] = {}
    for sim, row in scored:
        if row.lesson_id not in seen:
            seen[row.lesson_id] = (sim, row)
        if len(seen) >= top_k:
            break

    if not seen:
        return {
            "modules": [],
            "meta": {
                "backend": "python_cosine",
                "candidate_rows": len(rows),
                "invalid_embedding_rows": invalid_embedding_rows,
            },
        }

    modules = []
    for lesson_id, (sim, row) in seen.items():
        modules.append(
            {
                "lesson_id": lesson_id,
                "title": row.lesson_title,
                "chunk": row.chunk_text,
                "similarity": round(sim, 4),
                "is_read": False,
            }
        )

    modules, progress_lookup_ms = await _mark_read_progress(patient_id=patient_id, db=db, modules=modules)
    return {
        "modules": modules,
        "meta": {
            "backend": "python_cosine",
            "candidate_rows": len(rows),
            "invalid_embedding_rows": invalid_embedding_rows,
            "progress_lookup_ms": progress_lookup_ms,
        },
    }


async def _retrieve_with_pgvector(
    *,
    query_vec: list[float],
    patient_id: int,
    db: AsyncSession,
    top_k: int,
) -> dict[str, object]:
    query_vector = json.dumps(query_vec)
    rows_result = await db.execute(
        text(
            """
            SELECT le.lesson_id,
                   le.chunk_text,
                   le.card_index,
                   l.title AS lesson_title,
                   1 - (le.embedding_vector <=> CAST(:query_vector AS vector)) AS similarity
            FROM education.lesson_embeddings le
            JOIN education.lessons l ON l.id = le.lesson_id
            WHERE le.embedding_vector IS NOT NULL
            ORDER BY le.embedding_vector <=> CAST(:query_vector AS vector)
            LIMIT :candidate_limit
            """
        ),
        {"query_vector": query_vector, "candidate_limit": max(top_k * 5, top_k)},
    )
    rows = rows_result.fetchall()

    if not rows:
        return {
            "modules": [],
            "meta": {
                "backend": "pgvector",
                "candidate_rows": 0,
                "invalid_embedding_rows": 0,
            },
        }

    seen: dict[int, object] = {}
    for row in rows:
        if row.lesson_id not in seen:
            seen[row.lesson_id] = row
        if len(seen) >= top_k:
            break

    modules = []
    for row in seen.values():
        modules.append(
            {
                "lesson_id": row.lesson_id,
                "title": row.lesson_title,
                "chunk": row.chunk_text,
                "similarity": round(float(row.similarity or 0.0), 4),
                "is_read": False,
            }
        )

    modules, progress_lookup_ms = await _mark_read_progress(patient_id=patient_id, db=db, modules=modules)
    return {
        "modules": modules,
        "meta": {
            "backend": "pgvector",
            "candidate_rows": len(rows),
            "invalid_embedding_rows": 0,
            "progress_lookup_ms": progress_lookup_ms,
        },
    }


async def retrieve_relevant_modules_with_meta(
    query: str,
    patient_id: int,
    db: AsyncSession,
    top_k: int = 2,
) -> dict[str, object]:
    embedding_started = time.monotonic()
    try:
        query_vec = await _get_query_embedding(query)
    except (LLMTransportError, LLMResponseError) as exc:
        raise RetrievalError("failed to compute query embedding") from exc
    embedding_request_ms = int((time.monotonic() - embedding_started) * 1000)

    backend_info = await get_rag_backend_info(db)
    retrieval_started = time.monotonic()
    if backend_info["backend"] == "pgvector":
        result = await _retrieve_with_pgvector(
            query_vec=query_vec,
            patient_id=patient_id,
            db=db,
            top_k=top_k,
        )
    else:
        result = await _retrieve_with_python_cosine(
            query_vec=query_vec,
            patient_id=patient_id,
            db=db,
            top_k=top_k,
        )
    vector_search_ms = int((time.monotonic() - retrieval_started) * 1000)

    result["meta"].update(
        {
            "backend_selected": backend_info["backend"],
            "pgvector_extension_installed": backend_info["extension_installed"],
            "pgvector_column_present": backend_info["vector_column_present"],
            "pgvector_index_present": backend_info["vector_index_present"],
            "pgvector_blocker": backend_info["blocker"],
            "query_vector_dims": len(query_vec),
            "embedding_request_ms": embedding_request_ms,
            "vector_search_ms": vector_search_ms,
        }
    )
    return result


async def retrieve_relevant_modules(
    query: str,
    patient_id: int,
    db: AsyncSession,
    top_k: int = 2,
) -> list[dict]:
    result = await retrieve_relevant_modules_with_meta(query, patient_id, db, top_k=top_k)
    return list(result["modules"])
