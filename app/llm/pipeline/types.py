"""
Типы данных для LLM Pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.router import RouterResult


@dataclass
class LLMRequest:
    """Входящий запрос в LLM систему."""
    
    patient_id: int
    user_input: str
    source: str = "text"  # "text" | "button" | "system"
    
    # Опциональный контекст
    session_id: str | None = None
    thread_id: str | None = None
    daily_context: str = ""
    history: list[dict] = field(default_factory=list)
    orchestration_mode: str = "llm_full"  # "llm_full" | "specialist_rag" | "disabled"
    supervisor_state: dict[str, Any] | None = None
    
    # Database session
    db: AsyncSession | None = None


@dataclass
class LLMResponse:
    """Ответ LLM системы."""
    
    response: str
    tokens_input: int
    tokens_output: int
    model: str
    domain: str | None
    response_time_ms: int
    account_id: str | None
    
    # Дополнительные данные
    requested_model_tier: str
    actual_model_tier: str | None
    pending_vitals: list[dict] | None = None
    pending_st_memory: list[dict] = field(default_factory=list)
    pending_lt_memory: list[dict] = field(default_factory=list)
    supervisor_state: dict[str, Any] | None = None
    supervisor_state_delta: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineContext:
    """Контекст, передаваемый между stages pipeline."""
    
    # Исходный запрос
    request: LLMRequest
    
    # Результаты этапов
    classification: RouterResult | None = None
    patient_context: dict[str, Any] = field(default_factory=dict)
    memory_reads: dict[str, Any] = field(default_factory=dict)
    parser_result: dict[str, Any] = field(default_factory=dict)
    intake_result: Any = None
    orchestration_result: Any = None
    validation_result: Any = None
    supervisor_state: dict[str, Any] = field(default_factory=dict)
    supervisor_turn: Any = None
    response_draft: str | None = None
    
    # Диагностика
    diagnostics: dict[str, Any] = field(default_factory=dict)
    
    # Флаги управления
    should_skip_orchestration: bool = False
    early_response: str | None = None
    early_response_source: str | None = None


class PipelineStage(ABC):
    """Базовый класс для этапа pipeline."""
    
    @abstractmethod
    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Обрабатывает контекст и возвращает обновленный контекст.
        
        Args:
            context: Текущий контекст pipeline
            
        Returns:
            Обновленный контекст
        """
        pass
    
    @property
    @abstractmethod
    def stage_name(self) -> str:
        """Имя этапа для логирования."""
        pass
