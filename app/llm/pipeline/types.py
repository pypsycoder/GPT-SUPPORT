"""
Data types for the LLM pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.router import RouterResult


@dataclass
class LLMRequest:
    """Incoming request for the LLM pipeline."""

    patient_id: int
    user_input: str
    source: str = "text"  # "text" | "button" | "system"
    supervisor_state: dict[str, Any] | None = None
    router_result: RouterResult | None = None
    strict_model_tier: bool = False
    db: AsyncSession | None = None


@dataclass
class LLMResponse:
    """Pipeline response returned to callers."""

    response: str
    tokens_input: int
    tokens_output: int
    model: str
    domain: str | None
    response_time_ms: int
    account_id: str | None
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
    """Mutable context passed between pipeline stages."""

    request: LLMRequest
    classification: RouterResult | None = None
    supervisor_state: dict[str, Any] = field(default_factory=dict)
    supervisor_turn: Any = None
    response_draft: str | None = None
    response_tokens_input: int = 0
    response_tokens_output: int = 0
    response_account_id: str | None = None
    response_actual_model_tier: str | None = None
    education_rag_context: list[str] = field(default_factory=list)
    education_rag_grounding_items: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    early_response: str | None = None
    early_response_source: str | None = None


class PipelineStage(ABC):
    """Base class for pipeline stages."""

    @abstractmethod
    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process the context and return an updated context."""

    @property
    @abstractmethod
    def stage_name(self) -> str:
        """Stage name for diagnostics/logging."""
