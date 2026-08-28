"""
L1 — kNN по эмбеддингам прототипов (см. pipeline/STRUCTURE.md, «Роутер»).

Прототипы (``router_prototypes.SEED_PROTOTYPES``) эмбеддятся лениво при
первом вызове и кэшируются в процессе — тот же паттерн, что
``_QUERY_EMBEDDING_CACHE`` в ``app/rag/retriever.py`` до выноса в
``app.llm.embeddings``. Отдельной таблицы в БД не заводим: набор маленький
(74 примера) и меняется редко, пересчёт на рестарт стоит один batched вызов
``/embeddings``.

Как и L0, L1 не решает safety: класс "safety" исключён из прототипов на
этапе их отбора (см. ``router_prototypes.py``) — при сомнении в интенте
случайное попадание в safety через kNN было бы недопустимо шумным сигналом
на 1 примере обучающей выборки. Safety остаётся исключительно за L0.

Пороги ``threshold``/``margin`` взяты из манула "с потолка" — авторская
оговорка, не мой домысел. Проверять на реальном трафике см. часть 12,
пункт 7.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.llm.embeddings import cosine_similarity, get_text_embedding, get_text_embeddings_batch
from app.llm.errors import LLMError
from app.llm.router_prototypes import SEED_PROTOTYPES

logger = logging.getLogger("gpt-support-llm.router_l1")

# "с потолка", часть 8 манула — проверять на своих данных.
DEFAULT_THRESHOLD = 0.62
DEFAULT_MARGIN = 0.05


@dataclass(slots=True)
class L1Decision:
    """``request_type=None`` — kNN не уверен, решение за L2."""

    request_type: str | None = None
    confidence: float = 0.0
    margin: float = 0.0
    top_match: str | None = None

    @property
    def resolved(self) -> bool:
        return self.request_type is not None


_prototype_embeddings: list[tuple[str, str, list[float]]] | None = None
_prototype_lock = asyncio.Lock()


async def _ensure_prototype_embeddings() -> list[tuple[str, str, list[float]]]:
    """Считает эмбеддинги прототипов один раз за жизнь процесса, одним batched
    запросом — не 74 последовательных round-trip'а под общим локом аккаунта
    (что и происходило раньше, вопреки собственному докстрингу модуля)."""
    global _prototype_embeddings
    if _prototype_embeddings is not None:
        return _prototype_embeddings

    async with _prototype_lock:
        if _prototype_embeddings is not None:
            return _prototype_embeddings

        texts = [text for text, _ in SEED_PROTOTYPES]
        vectors = await get_text_embeddings_batch(texts)
        embedded = [
            (text, request_type, vec)
            for (text, request_type), vec in zip(SEED_PROTOTYPES, vectors)
        ]
        _prototype_embeddings = embedded
        logger.info("[router_l1] прототипы эмбеднуты: %d", len(embedded))
        return embedded


async def classify(
    text: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    margin: float = DEFAULT_MARGIN,
) -> L1Decision:
    """kNN (k=1 с проверкой отрыва от второго класса) по прототипам.

    Не бросает исключений наружу: любая сетевая/провайдерская ошибка —
    ``L1Decision()`` (не резолвлен), каскад откатится на L2 или на старый
    роутер. Роутинг не должен падать из-за недоступности embeddings API.
    """
    message = str(text or "").strip()
    if not message:
        return L1Decision()

    try:
        prototypes = await _ensure_prototype_embeddings()
        query_vec = await get_text_embedding(message)
    except LLMError as exc:
        logger.warning("[router_l1] embeddings недоступны: %s", exc)
        return L1Decision()

    scored = sorted(
        ((cosine_similarity(query_vec, vec), rtype, proto_text) for proto_text, rtype, vec in prototypes),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored:
        return L1Decision()

    best_sim, best_type, best_text = scored[0]
    if best_sim < threshold:
        return L1Decision(confidence=best_sim, top_match=best_text)

    # margin — отрыв от лучшего результата ДРУГОГО класса, а не просто от
    # второго места: несколько похожих прототипов одного класса подряд не
    # должны считаться "неуверенностью".
    runner_up_sim = next((sim for sim, rtype, _ in scored[1:] if rtype != best_type), 0.0)
    if best_sim - runner_up_sim < margin:
        return L1Decision(confidence=best_sim, margin=best_sim - runner_up_sim, top_match=best_text)

    return L1Decision(
        request_type=best_type,
        confidence=best_sim,
        margin=best_sim - runner_up_sim,
        top_match=best_text,
    )
