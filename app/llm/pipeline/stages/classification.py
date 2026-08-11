"""
Classification Stage - классификация запроса и проверка безопасности.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace

from app.llm import router_l0
from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.router import ModelTier, RequestType, classify_request
from app.llm.supervisor import CurrentState

logger = logging.getLogger("gpt-support-llm.pipeline.classification")


def _apply_l0_safety(context: PipelineContext) -> str | None:
    """Снять метку SAFETY, если L0 разобрал сообщение точнее.

    Без этого два классификатора спорят: L0 говорит «это запись показателя»,
    а keyword-роутер по числовому порогу продолжает считать то же сообщение
    кризисом и гнать его на max-тир. Кризисные ходы L0 при этом до сюда
    не доходят — их перехватывает BoundaryGuardStage.

    Понижаем метку только там, где L0 дал уверенный ответ. Совпадений
    «на всякий случай» не трогаем: правило про повышение приоритета в силе.
    """
    decision = context.l0
    if decision is None or not router_l0.l0_enabled():
        return None
    if context.classification.request_type is not RequestType.SAFETY:
        return None
    if decision.safety_level == "urgent" or not decision.resolved:
        return None

    tier = ModelTier.PRO if decision.safety_level == "concern" else context.classification.model_tier
    context.classification = replace(
        context.classification, request_type=RequestType.CLINICAL, model_tier=tier
    )
    logger.info(
        "[classification] L0 снял SAFETY: intent=%s rule=%s patient=%d",
        decision.intent,
        decision.rule,
        context.request.patient_id,
    )
    return f"{decision.intent}:{decision.rule}"


class ClassificationStage(PipelineStage):
    """
    Этап 1: Классификация запроса и boundary guards.
    
    Ответственность:
    - Классифицировать тип запроса (SAFETY, CLINICAL, EMOTIONAL, SIMPLE)
    - Определить модель (Lite, Pro, Max)
    - Определить домен (sleep, emotion, routine)
    - Проверить prompt injection
    - Проверить emergency vitals
    """
    
    @property
    def stage_name(self) -> str:
        return "classification"
    
    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()
        
        # Классификация запроса
        context.classification = context.request.router_result or classify_request(
            text=context.request.user_input,
            source=context.request.source
        )
        l0_override = _apply_l0_safety(context)
        context.supervisor_state = CurrentState.from_dict(context.request.supervisor_state).to_dict()

        # Диагностика
        context.diagnostics["classify"] = {
            "l0_safety_override": l0_override,
            "request_type": context.classification.request_type.value,
            "model_tier": context.classification.model_tier.value,
            "router_domain": context.classification.domain_hint,
            "effective_domain": context.classification.domain_hint,
            "priority": context.classification.priority,
            "supervisor_state_seeded": bool(context.request.supervisor_state),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
        
        logger.info(
            "[classification] patient=%d type=%s tier=%s domain=%s",
            context.request.patient_id,
            context.classification.request_type.value,
            context.classification.model_tier.value,
            context.classification.domain_hint or "-",
        )
        
        return context
