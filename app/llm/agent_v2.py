"""
Agent V2 - новая версия с использованием модульного pipeline.

Это обертка над LLMPipeline для обратной совместимости с существующим API.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.pipeline import LLMPipeline, LLMRequest
from app.llm.router import RouterResult

logger = logging.getLogger("gpt-support-llm.agent_v2")


# Глобальный экземпляр pipeline
_pipeline = LLMPipeline()


async def generate_response_v2(
    patient_id: int,
    user_input: str,
    router_result: RouterResult,
    context: dict,
    db: AsyncSession,
) -> dict:
    """
    Генерирует ответ LLM используя новый модульный pipeline.
    
    Это обертка для обратной совместимости с существующим API.
    В будущем можно полностью заменить старую generate_response().
    
    Args:
        patient_id: ID пациента
        user_input: текст запроса пользователя
        router_result: результат classify_request() (не используется, т.к. pipeline делает свою классификацию)
        context: дополнительный контекст (history, daily_context, orchestration_mode)
        db: AsyncSession для логирования
        
    Returns:
        dict с ответом в формате старого API
    """
    
    # Создаем запрос для pipeline
    request = LLMRequest(
        patient_id=patient_id,
        user_input=user_input,
        source=context.get("source", "text"),
        session_id=context.get("session_id"),
        thread_id=context.get("thread_id"),
        daily_context=context.get("daily_context", ""),
        history=context.get("history", []),
        orchestration_mode=context.get("orchestration_mode", "llm_full"),
        supervisor_state=context.get("supervisor_state"),
        router_result=router_result,
        strict_model_tier=bool(context.get("strict_model_tier", False)),
        db=db,
    )
    
    # Обрабатываем через pipeline
    response = await _pipeline.process(request)
    
    # Конвертируем в старый формат
    return {
        "response": response.response,
        "tokens_input": response.tokens_input,
        "tokens_output": response.tokens_output,
        "model": response.model,
        "domain": response.domain,
        "response_time_ms": response.response_time_ms,
        "account_id": response.account_id,
        "requested_model_tier": response.requested_model_tier,
        "actual_model_tier": response.actual_model_tier,
        "pending_vitals": response.pending_vitals,
        "pending_st_memory": response.pending_st_memory,
        "pending_lt_memory": response.pending_lt_memory,
        "supervisor_state": response.supervisor_state,
        "supervisor_state_delta": response.supervisor_state_delta,
        "diagnostics": response.diagnostics,
    }
