"""
RAG Retriever - retrieves relevant educational chunks for the current query.

Dense search: pgvector cosine similarity (falls back to Python cosine over
JSON-stored embeddings if the vector column/extension isn't available yet).
Sparse search: Postgres full-text search (to_tsvector('russian', ...) +
ts_rank_cd) over the generated `chunk_tsv` column — a real BM25-class ranker
with built-in Russian morphology, no external search engine required.

Dense and sparse candidate lists are combined with Reciprocal Rank Fusion
(RRF), which needs no score calibration between the two very different
scales (cosine similarity vs. ts_rank_cd).
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

# RRF constant — стандартное значение из литературы (Cormack et al.), не
# требует калибровки под масштаб конкретных скоров.
_RRF_K = 60


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


def _candidate_key(lesson_id: int, card_index: int) -> tuple[int, int]:
    return (int(lesson_id), int(card_index))


async def _sparse_search_bm25(
    *,
    query: str,
    db: AsyncSession,
    limit: int,
) -> list:
    result = await db.execute(
        text(
            """
            SELECT le.lesson_id,
                   le.chunk_text,
                   le.card_index,
                   l.title AS lesson_title,
                   l.code AS lesson_code,
                   l.topic AS lesson_topic,
                   ts_rank_cd(le.chunk_tsv, plainto_tsquery('russian', :query)) AS bm25_score
            FROM education.lesson_embeddings le
            JOIN education.lessons l ON l.id = le.lesson_id
            WHERE le.chunk_tsv @@ plainto_tsquery('russian', :query)
            ORDER BY bm25_score DESC
            LIMIT :limit
            """
        ),
        {"query": query, "limit": limit},
    )
    return result.fetchall()


def _reciprocal_rank_fusion(
    *,
    dense_keys: list[tuple[int, int]],
    sparse_keys: list[tuple[int, int]],
) -> dict[tuple[int, int], float]:
    scores: dict[tuple[int, int], float] = {}
    for rank, key in enumerate(dense_keys, start=1):
        scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
    for rank, key in enumerate(sparse_keys, start=1):
        scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
    return scores


def _build_candidate(
    *,
    row,
    vector_similarity: float | None,
    bm25_score: float | None,
    rrf_score: float,
    query_tokens: set[str],
) -> dict[str, object]:
    chunk_text = str(row.chunk_text)
    lesson_title = str(getattr(row, "lesson_title", ""))
    lesson_topic = str(getattr(row, "lesson_topic", "") or "")
    lesson_code = str(getattr(row, "lesson_code", "") or "")
    section_name = _extract_section_name(chunk_text)
    chunk_tokens = set(_tokenize(f"{lesson_title} {lesson_topic} {chunk_text}"))
    overlap_tokens = sorted(query_tokens & chunk_tokens)

    reasons: list[str] = []
    if vector_similarity is not None:
        reasons.append(f"vector={vector_similarity:.4f}")
    if bm25_score is not None:
        reasons.append(f"bm25={bm25_score:.4f}")
    reasons.append(f"rrf={rrf_score:.4f}")
    if overlap_tokens:
        reasons.append("lexical_overlap=" + ",".join(overlap_tokens[:6]))

    return {
        "lesson_id": int(row.lesson_id),
        "lesson_title": lesson_title,
        "lesson_topic": lesson_topic,
        "lesson_code": lesson_code,
        "card_index": int(getattr(row, "card_index", 0) or 0),
        "chunk_text": chunk_text,
        "chunk_preview": _clip_text(chunk_text),
        "section_name": section_name,
        "vector_similarity": round(float(vector_similarity), 4) if vector_similarity is not None else None,
        "bm25_score": round(float(bm25_score), 4) if bm25_score is not None else None,
        "hybrid_score": round(float(rrf_score), 4),
        "overlap_tokens": overlap_tokens,
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
            float(item["vector_similarity"] or 0.0),
            -int(item["card_index"]),
        ),
        reverse=True,
    )
    raw_ranked_candidates = [dict(item) for item in ranked_candidates]
    selected: list[dict[str, object]] = []
    covered_query_tokens: set[str] = set()

    # RRF-фьюжн даёт очень сжатые скоры (~1/k), а MMR-константы ниже
    # калиброваны под шкалу [0, 1] (косинусная близость). Нормализуем
    # hybrid_score в пределах кандидатного пула, чтобы диверсити-штрафы
    # значили то же самое независимо от источника скора.
    scores = [float(item["hybrid_score"]) for item in ranked_candidates]
    score_min = min(scores) if scores else 0.0
    score_max = max(scores) if scores else 0.0
    score_span = score_max - score_min

    def _normalized_score(item: dict[str, object]) -> float:
        if score_span <= 0:
            return 1.0
        return (float(item["hybrid_score"]) - score_min) / score_span

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

            mmr_score = _normalized_score(candidate) + coverage_bonus - redundancy_penalty
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


def _modules_from_candidates(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    modules = []
    for candidate in candidates:
        modules.append(
            {
                "lesson_id": candidate["lesson_id"],
                "title": candidate["lesson_title"],
                "topic": candidate["lesson_topic"],
                "code": candidate["lesson_code"],
                "card_index": candidate["card_index"],
                "chunk": candidate["chunk_text"],
                "similarity": candidate["vector_similarity"],
                "bm25_score": candidate["bm25_score"],
                "hybrid_score": candidate["hybrid_score"],
                "selection_reason": "; ".join(candidate.get("selection_reasons") or candidate["rerank_reasons"]),
            }
        )
    return modules


async def _fuse_and_select(
    *,
    query: str,
    dense_rows: list,
    db: AsyncSession,
    top_k: int,
    fulltext_available: bool,
) -> dict[str, object]:
    dense_by_key = {_candidate_key(row.lesson_id, row.card_index): row for row in dense_rows}
    dense_keys = list(dense_by_key.keys())

    sparse_rows = []
    if fulltext_available:
        sparse_rows = await _sparse_search_bm25(query=query, db=db, limit=max(top_k * 5, top_k))
    sparse_by_key = {_candidate_key(row.lesson_id, row.card_index): row for row in sparse_rows}
    sparse_keys = list(sparse_by_key.keys())

    rrf_scores = _reciprocal_rank_fusion(dense_keys=dense_keys, sparse_keys=sparse_keys)

    query_tokens = set(_tokenize(query))
    candidates: list[dict[str, object]] = []
    for key, rrf_score in rrf_scores.items():
        dense_row = dense_by_key.get(key)
        sparse_row = sparse_by_key.get(key)
        row = dense_row if dense_row is not None else sparse_row
        vector_similarity = float(dense_row.similarity) if dense_row is not None and hasattr(dense_row, "similarity") else None
        bm25_score = float(sparse_row.bm25_score) if sparse_row is not None else None
        candidates.append(
            _build_candidate(
                row=row,
                vector_similarity=vector_similarity,
                bm25_score=bm25_score,
                rrf_score=rrf_score,
                query_tokens=query_tokens,
            )
        )

    selected_candidates, ranked_candidates = _select_top_chunks(candidates=candidates, top_k=top_k)

    return {
        "modules": _modules_from_candidates(selected_candidates),
        "candidate_rows": len(dense_rows),
        "sparse_candidate_rows": len(sparse_rows),
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
    db: AsyncSession,
    top_k: int,
    fulltext_available: bool,
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
    dense_rows = rows_result.fetchall()

    fused = await _fuse_and_select(
        query=query,
        dense_rows=dense_rows,
        db=db,
        top_k=top_k,
        fulltext_available=fulltext_available,
    )
    return {
        "modules": fused["modules"],
        "meta": {
            "backend": "pgvector",
            "candidate_rows": fused["candidate_rows"],
            "sparse_candidate_rows": fused["sparse_candidate_rows"],
            "invalid_embedding_rows": 0,
            "progress_lookup_ms": 0,
        },
        "debug": fused["debug"],
    }


async def _retrieve_with_python_cosine(
    *,
    query: str,
    query_vec: list[float],
    db: AsyncSession,
    top_k: int,
    fulltext_available: bool,
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

    invalid_embedding_rows = 0
    scored_rows = []
    for row in rows:
        try:
            emb = json.loads(row.embedding)
            sim = _cosine_similarity(query_vec, emb)
            scored_rows.append((sim, row))
        except (json.JSONDecodeError, TypeError, ValueError):
            invalid_embedding_rows += 1

    if invalid_embedding_rows:
        logger.warning("[retriever] skipped %d malformed embedding rows", invalid_embedding_rows)

    scored_rows.sort(key=lambda item: item[0], reverse=True)
    top_dense = scored_rows[: max(top_k * 5, top_k)]

    class _DenseRow:
        def __init__(self, row, similarity: float) -> None:
            self.lesson_id = row.lesson_id
            self.chunk_text = row.chunk_text
            self.card_index = row.card_index
            self.lesson_title = getattr(row, "lesson_title", "")
            self.lesson_code = getattr(row, "lesson_code", "") or ""
            self.lesson_topic = getattr(row, "lesson_topic", "") or ""
            self.similarity = similarity

    dense_rows = [_DenseRow(row, sim) for sim, row in top_dense]

    fused = await _fuse_and_select(
        query=query,
        dense_rows=dense_rows,
        db=db,
        top_k=top_k,
        fulltext_available=fulltext_available,
    )
    return {
        "modules": fused["modules"],
        "meta": {
            "backend": "python_cosine",
            "candidate_rows": len(rows),
            "sparse_candidate_rows": fused["sparse_candidate_rows"],
            "invalid_embedding_rows": invalid_embedding_rows,
            "progress_lookup_ms": 0,
        },
        "debug": fused["debug"],
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
    fulltext_available = bool(backend_info.get("fulltext_column_present"))
    retrieval_started = time.monotonic()
    if backend_info["backend"] == "pgvector":
        result = await _retrieve_with_pgvector(
            query=query,
            query_vec=query_vec,
            db=db,
            top_k=top_k,
            fulltext_available=fulltext_available,
        )
    else:
        result = await _retrieve_with_python_cosine(
            query=query,
            query_vec=query_vec,
            db=db,
            top_k=top_k,
            fulltext_available=fulltext_available,
        )
    vector_search_ms = int((time.monotonic() - retrieval_started) * 1000)

    result["meta"].update(
        {
            "backend_selected": backend_info["backend"],
            "pgvector_extension_installed": backend_info["extension_installed"],
            "pgvector_column_present": backend_info["vector_column_present"],
            "pgvector_index_present": backend_info["vector_index_present"],
            "pgvector_blocker": backend_info["blocker"],
            "fulltext_column_present": fulltext_available,
            "fulltext_index_present": backend_info.get("fulltext_index_present"),
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
