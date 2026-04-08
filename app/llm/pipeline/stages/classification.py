"""
Classification Stage - классификация запроса и проверка безопасности.
"""

from __future__ import annotations

import logging
import time

from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.router import classify_request
from app.llm.supervisor import CurrentState

logger = logging.getLogger("gpt-support-llm.pipeline.classification")


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
        context.classification = classify_request(
            text=context.request.user_input,
            source=context.request.source
        )
        context.supervisor_state = CurrentState.from_dict(context.request.supervisor_state).to_dict()
        
        # Диагностика
        context.diagnostics["classify"] = {
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
