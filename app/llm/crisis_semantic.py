"""Семантический (embedding-based) второй эшелон детекции суицидального
риска — kNN по эмбеддингам, ПОВЕРХ regex L0, не вместо него.

Зачем отдельно от router_l1.py: L1 явно исключает safety из своих
прототипов ("слишком мало примеров, шумно для general-purpose роутера").
Этот модуль — специально построенный, только под одну задачу, с
собственным (гораздо большим) набором прототипов ``crisis_prototypes.py``
(22 позитив + 22 новых, не покрытых regex + 435 hard negative).

Место в пайплайне: вызывается из ``boundary_guard.py`` ПОСЛЕ regex L0,
только если L0 не дал urgent. Не заменяет L0 (тот бесплатный, 0мс,
детерминированный — незачем терять) — ловит только то, что L0 пропустил
по формулировке.

Как и L1, не бросает исключений наружу при сбое embeddings API —
семантический слой отсутствует, roditsya не должен ронять пайплайн.

Калибровка threshold/margin: см. ``scripts/patient_sim/calibrate_crisis_semantic.py``
и запись в ночном журнале — эмпирическая, на mined+drafted корпусе,
overnight-2026-08-27. Требует новой калибровки при существенном
расширении корпуса.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.llm.crisis_prototypes import NEGATIVE_MINED, POSITIVE_DRAFTED, POSITIVE_MINED
from app.llm.embeddings import cosine_similarity, get_text_embedding, get_text_embeddings_batch
from app.llm.errors import LLMError

logger = logging.getLogger("gpt-support-llm.crisis_semantic")

ENV_FLAG = "LLM_CRISIS_SEMANTIC"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Калибровка в два прохода (2026-08-27, semantic-layer-log.md):
# 1) leave-one-out на mined+drafted корпусе — margin=0.00 дал 100%/0% на
#    корпусе, тестирующем самого себя (оптимистично, не показательно).
# 2) РЕШАЮЩИЙ тест — 15 позитивов + 10 негативов, НИ ОДИН не входит в
#    прототипы, написаны отдельно как проверка обобщения. При margin=0.01
#    (leave-one-out значение) — recall 15/15, но false_pos 5/10 —
#    неприемлемо для авто-обрыва диалога. Свип по margin на ЭТОМ наборе:
#    0.03 → recall 15/15, false_pos 1/10 (не хуже regex — тот дал 1/15
#    recall! — при том же уровне ложных). 0.05+ режет recall быстрее,
#    чем ложные. threshold в диапазоне 0.65-0.85 не менял результат на
#    обоих корпусах — взят консервативно низкий край.
# Остаточный false positive на margin=0.03: "хочется всё бросить и
# уехать на море, отдохнуть" — лексически близко к позитивному прототипу
# про отказ от лечения ("подмывает всё бросить — и диализ"), но другой
# смысл (отпуск, не отчаяние). Известное ограничение, не патчил точечно.
DEFAULT_THRESHOLD = float(os.getenv("CRISIS_SEMANTIC_THRESHOLD", "0.70"))
DEFAULT_MARGIN = float(os.getenv("CRISIS_SEMANTIC_MARGIN", "0.03"))


def crisis_semantic_enabled() -> bool:
    return str(os.getenv(ENV_FLAG, "")).strip().lower() in _TRUTHY


@dataclass(slots=True)
class CrisisSemanticDecision:
    is_crisis: bool = False
    confidence: float = 0.0
    margin: float = 0.0
    nearest_positive: str | None = None
    nearest_negative: str | None = None


_prototype_vectors: tuple[list[tuple[str, list[float]]], list[tuple[str, list[float]]]] | None = None


async def _ensure_prototypes() -> tuple[list[tuple[str, list[float]]], list[tuple[str, list[float]]]]:
    global _prototype_vectors
    if _prototype_vectors is not None:
        return _prototype_vectors

    positive_texts = [*POSITIVE_MINED, *POSITIVE_DRAFTED]
    negative_texts = NEGATIVE_MINED

    pos_vecs = await get_text_embeddings_batch(positive_texts)
    neg_vecs = await get_text_embeddings_batch(negative_texts)

    positive = list(zip(positive_texts, pos_vecs))
    negative = list(zip(negative_texts, neg_vecs))
    _prototype_vectors = (positive, negative)
    logger.info(
        "[crisis_semantic] прототипы эмбеднуты: %d позитив, %d негатив",
        len(positive),
        len(negative),
    )
    return _prototype_vectors


async def classify(
    text: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    margin: float = DEFAULT_MARGIN,
) -> CrisisSemanticDecision:
    """kNN (k=1 к каждому классу) по прототипам суицидального риска.

    Срабатывает (``is_crisis=True``), только если ближайший позитивный
    прототип одновременно (а) не ниже порога сходства и (б) заметно ближе
    ближайшего негативного — то же правило margin, что у L1, чтобы не
    считать "уверенностью" общую эмоциональную окраску без разделяющего
    признака.
    """
    message = str(text or "").strip()
    if not message:
        return CrisisSemanticDecision()

    try:
        positive, negative = await _ensure_prototypes()
        query_vec = await get_text_embedding(message)
    except LLMError as exc:
        logger.warning("[crisis_semantic] embeddings недоступны: %s", exc)
        return CrisisSemanticDecision()

    best_pos_sim, best_pos_text = max(
        ((cosine_similarity(query_vec, vec), t) for t, vec in positive),
        default=(0.0, None),
    )
    best_neg_sim, best_neg_text = max(
        ((cosine_similarity(query_vec, vec), t) for t, vec in negative),
        default=(0.0, None),
    )

    decision = CrisisSemanticDecision(
        confidence=best_pos_sim,
        margin=best_pos_sim - best_neg_sim,
        nearest_positive=best_pos_text,
        nearest_negative=best_neg_text,
    )
    if best_pos_sim < threshold:
        return decision
    if best_pos_sim - best_neg_sim < margin:
        return decision

    decision.is_crisis = True
    return decision
