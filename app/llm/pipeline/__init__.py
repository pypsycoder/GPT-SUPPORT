"""
LLM Pipeline - модульная архитектура для обработки запросов.

Разбивает монолитную generate_response() на независимые stages:
1. Safety & Classification
2. Context & Memory
3. Intake & Clarification
4. Orchestration
5. Validation & Rewrite
6. Memory Write
"""

from app.llm.pipeline.types import (
    LLMRequest,
    LLMResponse,
    PipelineContext,
    PipelineStage,
)
from app.llm.pipeline.pipeline import LLMPipeline

__all__ = [
    "LLMRequest",
    "LLMResponse",
    "PipelineContext",
    "PipelineStage",
    "LLMPipeline",
]
