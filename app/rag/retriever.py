"""
RAG Retriever — поиск релевантных образовательных модулей по запросу пациента.

Эмбеддинги хранятся в TEXT (JSON-массив). Cosine similarity вычисляется на Python.

Публичный API:
    retrieve_relevant_modules(query, patient_id, db, top_k=2) -> list[dict]
"""

from __future__ import annotations

import json
import logging
import math

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("rag.retriever")

EMBEDDINGS_URL = "https://gigachat.devices.sberbank.ru/api/v1/embeddings"


async def _get_query_embedding(query: str) -> list[float]:
    """
    Получает эмбеддинг текста запроса через GigaChat Embeddings API.
    Использует существующий пул для авторизации.
    """
    from app.llm.pool import pool, _get_ssl_verify

    gc_client = await pool.get_available("lite")
    token = await gc_client._get_access_token()
    verify = _get_ssl_verify()

    async with httpx.AsyncClient(verify=verify, timeout=30.0) as http:
        resp = await http.post(
            EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"model": "Embeddings", "input": [query]},
        )
        resp.raise_for_status()
        data = resp.json()

    return data["data"][0]["embedding"]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Косинусное сходство двух векторов."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def retrieve_relevant_modules(
    query: str,
    patient_id: int,
    db: AsyncSession,
    top_k: int = 2,
) -> list[dict]:
    """
    Находит top_k образовательных модулей, наиболее релевантных запросу.

    Алгоритм:
    1. Получить эмбеддинг query через GigaChat Embeddings API
    2. Загрузить все эмбеддинги из БД и вычислить cosine similarity на Python
    3. Для top_k найденных уроков проверить статус прочтения пациентом
    4. Вернуть дедуплицированный список (один урок — один результат)

    Returns:
        Список словарей:
        [{"lesson_id": 1, "title": "Стресс", "chunk": "...",
          "similarity": 0.87, "is_read": True}]
    """
    query_vec = await _get_query_embedding(query)

    # Загружаем все чанки с эмбеддингами из БД
    rows_result = await db.execute(
        text("""
            SELECT le.lesson_id,
                   le.chunk_text,
                   le.card_index,
                   le.embedding,
                   l.title AS lesson_title
            FROM education.lesson_embeddings le
            JOIN education.lessons l ON l.id = le.lesson_id
            WHERE le.embedding IS NOT NULL
        """)
    )
    rows = rows_result.fetchall()

    if not rows:
        return []

    # Вычисляем cosine similarity для каждого чанка
    scored: list[tuple[float, object]] = []
    for row in rows:
        try:
            emb = json.loads(row.embedding)
            sim = _cosine_similarity(query_vec, emb)
            scored.append((sim, row))
        except Exception:
            continue

    # Сортируем по убыванию сходства
    scored.sort(key=lambda x: x[0], reverse=True)

    # Дедупликация по lesson_id — берём наиболее релевантный чанк
    seen: dict[int, tuple[float, object]] = {}
    for sim, row in scored:
        if row.lesson_id not in seen:
            seen[row.lesson_id] = (sim, row)
        if len(seen) >= top_k:
            break

    if not seen:
        return []

    # Проверяем прочитанные уроки пациента
    lesson_ids = list(seen.keys())
    progress_result = await db.execute(
        text("""
            SELECT lesson_id
            FROM education.lesson_progress
            WHERE user_id = :patient_id
              AND is_completed = true
              AND lesson_id = ANY(:lesson_ids)
        """),
        {"patient_id": patient_id, "lesson_ids": lesson_ids},
    )
    read_ids: set[int] = {row[0] for row in progress_result.fetchall()}

    result = []
    for lesson_id, (sim, row) in seen.items():
        result.append({
            "lesson_id": lesson_id,
            "title": row.lesson_title,
            "chunk": row.chunk_text,
            "similarity": round(sim, 4),
            "is_read": lesson_id in read_ids,
        })

    return result
