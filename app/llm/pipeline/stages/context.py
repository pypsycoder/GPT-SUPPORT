"""
Context Stage - сбор контекста пациента и чтение памяти.
"""

from __future__ import annotations

import logging
import os
import time

from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.router import RequestType

logger = logging.getLogger("gpt-support-llm.pipeline.context")

# Feature flag для оптимизированной версии
USE_OPTIMIZED_CONTEXT_BUILDER = os.getenv("LLM_USE_OPTIMIZED_CONTEXT", "true").lower() == "true"


def _build_memory_reads(context_data: dict) -> dict[str, object]:
    """Извлекает memory reads из контекста."""
    st_items = list(context_data.get("st_memory") or [])
    lt_items = list(context_data.get("lt_memory") or [])
    return {
        "st_items": st_items,
        "lt_items": lt_items,
        "st_count": len(st_items),
        "lt_count": len(lt_items),
    }


class ContextStage(PipelineStage):
    """
    Этап 2: Сбор контекста пациента и чтение памяти.
    
    Ответственность:
    - Собрать витальные показатели, лекарства, сон
    - Выполнить RAG поиск (если нужен)
    - Прочитать ST/LT память
    - Построить patient summary
    """
    
    @property
    def stage_name(self) -> str:
        return "context"
    
    async def process(self, context: PipelineContext) -> PipelineContext:
        if context.supervisor_turn is not None:
            if context.patient_context:
                context.memory_reads = _build_memory_reads(context.patient_context)
                existing_patient_context = dict(context.diagnostics.get("patient_context") or {})
                existing_memory = dict(context.diagnostics.get("memory") or {})
                context.diagnostics["patient_context"] = {
                    **existing_patient_context,
                    "skipped": True,
                    "reason": "supervisor_turn",
                    "source": "supervisor_prefetch",
                }
                context.diagnostics["memory"] = {
                    **existing_memory,
                    "reads": context.memory_reads,
                    "skipped": True,
                    "reason": "supervisor_turn",
                }
            else:
                context.diagnostics["patient_context"] = {"skipped": True, "reason": "supervisor_turn"}
                context.diagnostics["memory"] = {"reads": {}, "skipped": True}
            return context

        started = time.monotonic()
        
        # Для кнопок RAG не нужен
        rag_query = "" if context.classification.request_type == RequestType.QUICK_ACTION else context.request.user_input
        
        # Выбираем версию context builder
        if USE_OPTIMIZED_CONTEXT_BUILDER:
            from app.llm.context_builder_optimized import build_context_bundle_optimized
            context_bundle = await build_context_bundle_optimized(
                context.request.patient_id,
                context.request.db,
                query=rag_query
            )
            logger.debug("[context] using optimized context builder")
        else:
            from app.llm.context_builder import build_context_bundle
            context_bundle = await build_context_bundle(
                context.request.patient_id,
                context.request.db,
                query=rag_query
            )
            logger.debug("[context] using legacy context builder")
        
        context.patient_context = context_bundle["context"]
        context.memory_reads = _build_memory_reads(context.patient_context)
        
        # Диагностика
        context.diagnostics["patient_context"] = context_bundle["diagnostics"]
        context.diagnostics["memory"] = {
            "reads": context.memory_reads,
        }
        
        logger.info(
            "[context] patient=%d sections_ok=%d sections_failed=%d rag_hits=%d st_memory=%d lt_memory=%d latency_ms=%d",
            context.request.patient_id,
            len(context_bundle["diagnostics"].get("sections_ok", [])),
            len(context_bundle["diagnostics"].get("sections_failed", [])),
            context_bundle["diagnostics"].get("rag", {}).get("hit_count", 0),
            context.memory_reads["st_count"],
            context.memory_reads["lt_count"],
            int((time.monotonic() - started) * 1000),
        )
        
        return context
