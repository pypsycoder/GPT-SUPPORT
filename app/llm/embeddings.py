"""
Общий клиент эмбеддингов GigaChat.

Вынесен из ``app/rag/retriever.py`` (было ``_get_query_embedding`` /
``_cosine_similarity``, дублировать для роутера L1 незачем — логика и кэш
по тексту в процессе те же).
"""

from __future__ import annotations

import math
from collections import OrderedDict

from app.llm.errors import LLMResponseError
from app.llm.http import request_json_with_policy

EMBEDDINGS_URL = "https://gigachat.devices.sberbank.ru/api/v1/embeddings"

# Кэш раньше питали только RAG-запросы (реально повторяются между пациентами
# и во времени), теперь ещё и сырые реплики пациентов из router_l1 — они
# почти всегда уникальны, кэш только рос бы без предела и без TTL копил
# сырой текст сообщений. LRU с потолком — не бесконечный рост, реальный
# повтор (частые RAG-запросы) выживает дольше редкого.
_EMBEDDING_CACHE_MAX_SIZE = 2000
_EMBEDDING_CACHE: "OrderedDict[str, list[float]]" = OrderedDict()


def _cache_get(text: str) -> list[float] | None:
    cached = _EMBEDDING_CACHE.get(text)
    if cached is not None:
        _EMBEDDING_CACHE.move_to_end(text)
    return cached


def _cache_put(text: str, embedding: list[float]) -> None:
    _EMBEDDING_CACHE[text] = list(embedding)
    _EMBEDDING_CACHE.move_to_end(text)
    while len(_EMBEDDING_CACHE) > _EMBEDDING_CACHE_MAX_SIZE:
        _EMBEDDING_CACHE.popitem(last=False)


async def get_text_embedding(text: str) -> list[float]:
    """Эмбеддинг текста через GigaChat ``/embeddings``, с LRU-кэшем по точному тексту."""
    cached = _cache_get(text)
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
            operation="text embedding",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json_body={"model": "Embeddings", "input": [text]},
        )
        embedding = data["data"][0]["embedding"]
        _cache_put(text, embedding)
        return embedding
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMResponseError("embeddings response payload is invalid") from exc


async def get_text_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Эмбеддинги нескольких текстов ОДНИМ запросом (``input`` принимает список,
    как в ``app/rag/indexer.py``). Для холодного старта L1 (74 прототипа) —
    иначе 74 последовательных round-trip'а под общим локом аккаунта.

    Уже закэшированные тексты в запрос не попадают; порядок результата
    соответствует порядку ``texts``, включая кэш-хиты.
    """
    fetched: dict[str, list[float]] = {}
    to_fetch = [t for t in texts if _cache_get(t) is None]
    if to_fetch:
        from app.llm.pool import pool

        gc_client = await pool.get_available("lite")
        token = await gc_client._get_access_token()

        try:
            data = await request_json_with_policy(
                "embeddings",
                method="POST",
                url=EMBEDDINGS_URL,
                operation="batch text embeddings",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json_body={"model": "Embeddings", "input": to_fetch},
            )
            items = sorted(data["data"], key=lambda x: x["index"])
            if len(items) != len(to_fetch):
                raise LLMResponseError("batch embeddings response size mismatch")
            for text, item in zip(to_fetch, items):
                embedding = list(item["embedding"])
                fetched[text] = embedding
                _cache_put(text, embedding)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMResponseError("batch embeddings response payload is invalid") from exc

    # Не полагаемся на повторное чтение кэша для свежих значений: при батче
    # больше _EMBEDDING_CACHE_MAX_SIZE LRU-вытеснение внутри цикла _cache_put
    # выше могло бы успеть выселить запись, которую сейчас же нужно вернуть.
    return [fetched[t] if t in fetched else list(_cache_get(t) or []) for t in texts]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
