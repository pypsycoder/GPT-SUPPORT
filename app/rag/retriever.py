"""
RAG Retriever - retrieves relevant educational chunks for the current query.

Embeddings are currently stored as JSON strings in TEXT columns.
Similarity is still computed in Python until pgvector migration.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.errors import LLMResponseError, LLMTransportError, RetrievalError
from app.llm.http import request_json_with_policy
from app.rag.capabilities import get_rag_backend_info


logger = logging.getLogger("rag.retriever")

EMBEDDINGS_URL = "https://gigachat.devices.sberbank.ru/api/v1/embeddings"
_QUERY_EMBEDDING_CACHE: dict[str, list[float]] = {}
_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+")
_SECTION_RE = re.compile(r"##\s*\[([^\]]+)\]")
_SECTION_FALLBACK_RE = re.compile(r"Раздел:\s*([^\n]+)")
_GENERIC_SECTION_PENALTIES = {
    "actions": -0.03,
    "anchor": -0.04,
}
_ACTION_HINT_TOKENS = {
    "что",
    "сделать",
    "делать",
    "помочь",
    "поможет",
    "попробовать",
    "шаг",
    "шаги",
    "наладить",
    "как",
}
_RUSSIAN_SUFFIXES = (
    "иями",
    "ями",
    "ами",
    "его",
    "ого",
    "ему",
    "ому",
    "иях",
    "ах",
    "ях",
    "ия",
    "ья",
    "ие",
    "ые",
    "ий",
    "ый",
    "ой",
    "ая",
    "яя",
    "ое",
    "ее",
    "ам",
    "ям",
    "ом",
    "ем",
    "ую",
    "юю",
    "ов",
    "ев",
    "ей",
    "ы",
    "и",
    "а",
    "я",
    "е",
    "у",
    "ю",
)


async def _get_query_embedding(query: str) -> list[float]:
    cached = _QUERY_EMBEDDING_CACHE.get(query)
    if cached is not None:
        return list(cached)

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
        embedding = data["data"][0]["embedding"]
        _QUERY_EMBEDDING_CACHE[query] = list(embedding)
        return embedding
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMResponseError("embeddings response payload is invalid") from exc


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalize_token(token: str) -> str:
    normalized = token.strip().lower().replace("ё", "е")
    for suffix in _RUSSIAN_SUFFIXES:
        if len(normalized) > 4 and normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _tokenize(text_value: str) -> list[str]:
    tokens = [_normalize_token(match.group(0)) for match in _TOKEN_RE.finditer(text_value)]
    return [token for token in tokens if len(token) >= 3]


def _extract_section_name(chunk_text: str) -> str | None:
    match = _SECTION_RE.search(chunk_text)
    if match:
        return match.group(1).strip().lower()
    fallback = _SECTION_FALLBACK_RE.search(chunk_text)
    if fallback:
        return fallback.group(1).strip().lower()
    return None


def _clip_text(text_value: str, limit: int = 260) -> str:
    compact = " ".join(text_value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _build_candidate_debug(
    *,
    row,
    similarity: float,
    query_tokens: set[str],
) -> dict[str, object]:
    chunk_text = str(row.chunk_text)
    lesson_title = str(getattr(row, "lesson_title", ""))
    lesson_topic = str(getattr(row, "lesson_topic", "") or "")
    lesson_code = str(getattr(row, "lesson_code", "") or "")
    section_name = _extract_section_name(chunk_text)
    chunk_tokens = set(_tokenize(f"{lesson_title} {lesson_topic} {chunk_text}"))
    overlap_tokens = sorted(query_tokens & chunk_tokens)
    overlap_ratio = (len(overlap_tokens) / len(query_tokens)) if query_tokens else 0.0

    section_penalty = 0.0
    if section_name in _GENERIC_SECTION_PENALTIES:
        if not (query_tokens & _ACTION_HINT_TOKENS):
            section_penalty = _GENERIC_SECTION_PENALTIES[section_name]

    title_token_bonus = 0.015 if query_tokens & set(_tokenize(lesson_title)) else 0.0
    topic_token_bonus = 0.01 if query_tokens & set(_tokenize(lesson_topic.replace("-", " "))) else 0.0
    lexical_bonus = overlap_ratio * 0.14
    final_score = float(similarity) + lexical_bonus + title_token_bonus + topic_token_bonus + section_penalty

    reasons: list[str] = [f"vector={similarity:.4f}"]
    if overlap_tokens:
        reasons.append(
            "lexical_overlap="
            + ",".join(overlap_tokens[:6])
            + f" (+{lexical_bonus:.4f})"
        )
    if title_token_bonus:
        reasons.append(f"title_match (+{title_token_bonus:.4f})")
    if topic_token_bonus:
        reasons.append(f"topic_match (+{topic_token_bonus:.4f})")
    if section_penalty:
        reasons.append(f"generic_section_penalty ({section_penalty:.4f})")

    return {
        "lesson_id": int(row.lesson_id),
        "lesson_title": lesson_title,
        "lesson_topic": lesson_topic,
        "lesson_code": lesson_code,
        "card_index": int(getattr(row, "card_index", 0) or 0),
        "chunk_text": chunk_text,
        "chunk_preview": _clip_text(chunk_text),
        "section_name": section_name,
        "vector_similarity": round(float(similarity), 4),
        "overlap_tokens": overlap_tokens,
        "overlap_ratio": round(overlap_ratio, 4),
        "hybrid_score": round(final_score, 4),
        "rerank_reasons": reasons,
    }


def _select_top_chunks(
    *,
    candidates: list[dict[str, object]],
    top_k: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ranked_candidates = sorted(
        candidates,
        key=lambda item: (
            float(item["hybrid_score"]),
            float(item["vector_similarity"]),
            -int(item["card_index"]),
        ),
        reverse=True,
    )
    raw_ranked_candidates = [dict(item) for item in ranked_candidates]
    selected: list[dict[str, object]] = []
    covered_query_tokens: set[str] = set()

    while ranked_candidates and len(selected) < top_k:
        best_candidate: dict[str, object] | None = None
        best_score = float("-inf")

        for candidate in ranked_candidates:
            candidate_tokens = set(candidate.get("overlap_tokens") or [])
            new_tokens = candidate_tokens - covered_query_tokens
            coverage_bonus = 0.02 * len(new_tokens)

            redundancy_penalty = 0.0
            for existing in selected:
                existing_tokens = set(existing.get("overlap_tokens") or [])
                shared = candidate_tokens & existing_tokens
                if shared:
                    redundancy_penalty += 0.018 * len(shared)
                if candidate["lesson_id"] == existing["lesson_id"]:
                    redundancy_penalty += 0.035
                if candidate.get("section_name") == existing.get("section_name"):
                    redundancy_penalty += 0.01

            mmr_score = float(candidate["hybrid_score"]) + coverage_bonus - redundancy_penalty
            reasons = list(candidate.get("rerank_reasons", []))
            if new_tokens:
                reasons.append(
                    "coverage_bonus="
                    + ",".join(sorted(new_tokens)[:6])
                    + f" (+{coverage_bonus:.4f})"
                )
            if redundancy_penalty:
                reasons.append(f"redundancy_penalty (-{redundancy_penalty:.4f})")

            candidate["selection_score"] = round(mmr_score, 4)
            candidate["selection_reasons"] = reasons

            if mmr_score > best_score:
                best_score = mmr_score
                best_candidate = candidate

        if best_candidate is None:
            break

        selected.append(best_candidate)
        covered_query_tokens.update(best_candidate.get("overlap_tokens") or [])
        ranked_candidates = [item for item in ranked_candidates if item is not best_candidate]

    return selected, raw_ranked_candidates


async def _retrieve_with_python_cosine(
    *,
    query: str,
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
                   l.title AS lesson_title,
                   l.code AS lesson_code,
                   l.topic AS lesson_topic
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

    scored: list[dict[str, object]] = []
    invalid_embedding_rows = 0
    query_tokens = set(_tokenize(query))
    for row in rows:
        try:
            emb = json.loads(row.embedding)
            sim = _cosine_similarity(query_vec, emb)
            scored.append(_build_candidate_debug(row=row, similarity=sim, query_tokens=query_tokens))
        except (json.JSONDecodeError, TypeError, ValueError):
            invalid_embedding_rows += 1

    if invalid_embedding_rows:
        logger.warning("[retriever] skipped %d malformed embedding rows", invalid_embedding_rows)

    selected_candidates, ranked_candidates = _select_top_chunks(candidates=scored, top_k=top_k)

    if not selected_candidates:
        return {
            "modules": [],
            "meta": {
                "backend": "python_cosine",
                "candidate_rows": len(rows),
                "invalid_embedding_rows": invalid_embedding_rows,
            },
            "debug": {
                "query": query,
                "raw_candidates": ranked_candidates[: max(top_k * 4, top_k)],
                "selected_candidates": [],
            },
        }

    modules = []
    for candidate in selected_candidates:
        modules.append(
            {
                "lesson_id": candidate["lesson_id"],
                "title": candidate["lesson_title"],
                "topic": candidate["lesson_topic"],
                "code": candidate["lesson_code"],
                "card_index": candidate["card_index"],
                "chunk": candidate["chunk_text"],
                "similarity": candidate["vector_similarity"],
                "hybrid_score": candidate["hybrid_score"],
                "selection_reason": "; ".join(candidate.get("selection_reasons") or candidate["rerank_reasons"]),
            }
        )

    return {
        "modules": modules,
        "meta": {
            "backend": "python_cosine",
            "candidate_rows": len(rows),
            "invalid_embedding_rows": invalid_embedding_rows,
            "progress_lookup_ms": 0,
        },
        "debug": {
            "query": query,
            "raw_candidates": ranked_candidates[: max(top_k * 4, top_k)],
            "selected_candidates": selected_candidates,
        },
    }


async def _retrieve_with_pgvector(
    *,
    query: str,
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
                   l.code AS lesson_code,
                   l.topic AS lesson_topic,
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

    query_tokens = set(_tokenize(query))
    candidate_debug = [
        _build_candidate_debug(
            row=row,
            similarity=float(row.similarity or 0.0),
            query_tokens=query_tokens,
        )
        for row in rows
    ]
    selected_candidates, ranked_candidates = _select_top_chunks(
        candidates=candidate_debug,
        top_k=top_k,
    )

    modules = []
    for candidate in selected_candidates:
        modules.append(
            {
                "lesson_id": candidate["lesson_id"],
                "title": candidate["lesson_title"],
                "topic": candidate["lesson_topic"],
                "code": candidate["lesson_code"],
                "card_index": candidate["card_index"],
                "chunk": candidate["chunk_text"],
                "similarity": candidate["vector_similarity"],
                "hybrid_score": candidate["hybrid_score"],
                "selection_reason": "; ".join(candidate.get("selection_reasons") or candidate["rerank_reasons"]),
            }
        )

    return {
        "modules": modules,
        "meta": {
            "backend": "pgvector",
            "candidate_rows": len(rows),
            "invalid_embedding_rows": 0,
            "progress_lookup_ms": 0,
        },
        "debug": {
            "query": query,
            "raw_candidates": ranked_candidates[: max(top_k * 4, top_k)],
            "selected_candidates": selected_candidates,
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
            query=query,
            query_vec=query_vec,
            patient_id=patient_id,
            db=db,
            top_k=top_k,
        )
    else:
        result = await _retrieve_with_python_cosine(
            query=query,
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
