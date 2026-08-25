"""
Каскадный роутер (00_MANUAL.md, часть 8): L0 → L1 → L2 → старый keyword-роутер.

Каждый следующий уровень дороже и вызывается только если предыдущий не дал
уверенного ответа. Заменяет то, что раньше решали
``router.classify_request``'s ``SAFETY_KEYWORDS``/``CLINICAL_KEYWORDS``/
``EMOTIONAL_KEYWORDS`` (совпадение по подстроке — см. докстринг
``router_l0.py`` про «покончить с этим делом»).

Число из ``scripts/eval_router_l0.py`` на ``LLM_test/cases/intent_labels.json``:
старый роутер на 104 сообщениях пропустил единственный настоящий кризис и
ложно пометил SAFETY «У меня давление 200 на 100» (в ответ пациенту
дописывается номер телефона доверия — ``pipeline.py::_build_response``).
L0 поймал кризис и не дал ни одного ложного срабатывания, но уверенно
отвечает только на 13% сообщений — остальные идут дальше по каскаду.

Отказоустойчивость: любая ошибка на любом уровне (сеть, невалидный JSON,
провайдер недоступен) — откат на синхронный ``classify_request`` целиком.
Каскад не должен ронять запрос пациента только потому, что embeddings API
недоступен.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from app.llm import router_l0, router_l1, router_l2
from app.llm.router import ModelTier, RequestType, RouterResult, classify_request, detect_domain

logger = logging.getLogger("gpt-support-llm.router_cascade")

_TIER_RANK = {ModelTier.LITE: 0, ModelTier.PRO: 1, ModelTier.MAX: 2}

_SHORT_TEXT_CHARS = 30

_TYPE_MAP = {
    "simple": RequestType.SIMPLE,
    "clinical": RequestType.CLINICAL,
    "emotional": RequestType.EMOTIONAL,
    "safety": RequestType.SAFETY,
}


def _map_request_type(request_type_str: str, text: str, domain: str | None) -> RouterResult:
    request_type = _TYPE_MAP.get(request_type_str, RequestType.SIMPLE)

    if request_type is RequestType.SAFETY:
        return RouterResult(RequestType.SAFETY, ModelTier.MAX, domain, 3)
    if request_type is RequestType.CLINICAL:
        return RouterResult(RequestType.CLINICAL, ModelTier.PRO, domain, 2)
    if request_type is RequestType.EMOTIONAL:
        return RouterResult(RequestType.EMOTIONAL, ModelTier.PRO, domain, 2)

    # simple: короткая реплика — Lite, иначе Pro (правило 6/7 старого роутера).
    tier = ModelTier.LITE if len(text.strip()) < _SHORT_TEXT_CHARS else ModelTier.PRO
    return RouterResult(RequestType.SIMPLE, tier, domain, 1)


def _apply_floor(
    result: RouterResult, floor_tier: ModelTier | None, floor_priority: int | None
) -> RouterResult:
    """L0 concern поднимает планку тира/приоритета, но никогда не снижает её.

    Тот же принцип, что уже в ``router_l0.py``: стоп-слова только повышают.
    """
    if floor_tier is None or result.request_type is RequestType.SAFETY:
        return result

    tier = floor_tier if _TIER_RANK[floor_tier] > _TIER_RANK[result.model_tier] else result.model_tier
    priority = max(result.priority, floor_priority or 0)
    if tier == result.model_tier and priority == result.priority:
        return result
    return replace(result, model_tier=tier, priority=priority)


async def classify_request_async(text: str, source: str) -> RouterResult:
    """Асинхронная замена ``classify_request`` — с каскадом L0/L1/L2.

    Единственная точка входа для нового роутинга. При отключённых флагах или
    любой ошибке ведёт себя ровно как старый ``classify_request``.
    """
    if source == "button":
        return classify_request(text, source)

    try:
        domain = detect_domain(text)

        floor_tier: ModelTier | None = None
        floor_priority: int | None = None

        if router_l0.l0_enabled():
            decision = router_l0.classify(text)
            if decision.safety_level == "urgent":
                return RouterResult(RequestType.SAFETY, ModelTier.MAX, domain, 3)
            if decision.safety_level == "concern":
                floor_tier = ModelTier.PRO
                floor_priority = 2
            if decision.intent == "data_entry":
                # Регрессия, пойманная при написании MANUAL_TEST_PLAN.md: без
                # этой ветки L0 только поднимал планку (concern), но никогда
                # не резолвил тип сам — "давление 200 на 100" при ОДНОМ
                # включённом LLM_ROUTER_L0 (без L1/L2) проваливалось в старый
                # classify_request и оставалось SAFETY. L0 явно резолвит
                # data_entry (см. router_l0.classify) — CLINICAL прямо здесь,
                # не дожидаясь L1/L2/отката.
                result = RouterResult(RequestType.CLINICAL, ModelTier.PRO, domain, 2)
                return _apply_floor(result, floor_tier, floor_priority)

        request_type_str: str | None = None
        resolved_by = "fallback"

        if router_l1.l1_enabled():
            l1_decision = await router_l1.classify(text)
            if l1_decision.resolved:
                request_type_str = l1_decision.request_type
                resolved_by = "l1"

        if request_type_str is None and router_l2.l2_enabled():
            l2_type = await router_l2.classify(text)
            if l2_type is not None:
                request_type_str = l2_type
                resolved_by = "l2"

        if request_type_str is None:
            result = classify_request(text, source)
        else:
            result = _map_request_type(request_type_str, text, domain)
            # PROACTIVE — старое поведение для system-сообщений, которые
            # каскад не смог отнести ни к чему конкретному. Тир и приоритет
            # тоже фиксируем как в старом classify_request (PRO/1 всегда для
            # source == "system"), а не только тип: _map_request_type для
            # "simple" мог отдать LITE на короткой реплике — иначе полной
            # эквивалентности со старым роутером не было бы.
            if source == "system" and result.request_type is RequestType.SIMPLE:
                result = replace(result, request_type=RequestType.PROACTIVE, model_tier=ModelTier.PRO, priority=1)

        result = _apply_floor(result, floor_tier, floor_priority)
        logger.debug(
            "[router_cascade] resolved_by=%s type=%s tier=%s",
            resolved_by, result.request_type.value, result.model_tier.value,
        )
        return result
    except Exception as exc:  # noqa: BLE001 — роутинг не должен ронять запрос
        logger.exception("[router_cascade] cascade failed, falling back: %s", exc)
        return classify_request(text, source)
