"""Stateful supervisor MVP with compatibility re-exports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.llm.router import RequestType
from app.llm.supervisor.classification import classify_message
from app.llm.supervisor.models import (
    CurrentState,
    ExpertResult,
    ExpertTask,
    PendingQuestion,
    SupervisorTurnResult,
)
from app.llm.supervisor.short_answers import normalize_short_answer, try_parse_pending_answer
from app.llm.supervisor.state_merge import merge_state_delta

USE_LLM_SUPERVISOR = False


class AmbiguityType(str, Enum):
    DOMAIN_AMBIGUITY = "domain_ambiguity"
    INTENT_AMBIGUITY = "intent_ambiguity"
    VAGUE_GOAL = "vague_goal"
    CONTEXTUAL_REFERENCE = "contextual_reference"
    CONFLICT_OR_CORRECTION = "conflict_or_correction"


@dataclass(slots=True)
class SupervisorDecision:
    needs_clarification: bool
    ambiguity_type: AmbiguityType | None
    clarification_question: str | None
    routing_hint: dict[str, object] | None
    confidence: float
    reasoning: list[str]


class Supervisor:
    def analyze(
        self,
        user_input: str,
        *,
        parser_mood: str | None = None,
        parser_domain_hints: list[str] | None = None,
        st_memory: list[dict] | None = None,
    ) -> SupervisorDecision:
        state = CurrentState()
        classification = classify_message(user_input, state)
        needs_clarification = classification["message_type"] == "correction" or not classification["goal"]
        ambiguity_type = AmbiguityType.CONFLICT_OR_CORRECTION if classification["message_type"] == "correction" else None
        if not ambiguity_type and not classification["goal"]:
            ambiguity_type = AmbiguityType.VAGUE_GOAL
        question = "Что сейчас беспокоит тебя больше всего?" if needs_clarification else None
        return SupervisorDecision(
            needs_clarification=needs_clarification,
            ambiguity_type=ambiguity_type,
            clarification_question=question,
            routing_hint={"suggested_domain": classification["domain"]} if not needs_clarification else None,
            confidence=0.8,
            reasoning=[classification["intent"], classification["domain"]],
        )


class LLMSupervisor(Supervisor):
    async def analyze(self, *args, **kwargs) -> SupervisorDecision:  # type: ignore[override]
        return super().analyze(*args, **kwargs)


def should_use_supervisor(user_input: str, classification: object, intake_result: object | None = None) -> bool:
    if hasattr(classification, "request_type") and classification.request_type in {
        RequestType.SAFETY,
        RequestType.QUICK_ACTION,
    }:
        return False
    return bool(str(user_input or "").strip())


def __getattr__(name: str):
    if name == "SupervisorOrchestrator":
        from app.llm.supervisor.orchestrator import SupervisorOrchestrator

        return SupervisorOrchestrator
    raise AttributeError(name)


__all__ = [
    "AmbiguityType",
    "CurrentState",
    "ExpertResult",
    "ExpertTask",
    "LLMSupervisor",
    "PendingQuestion",
    "Supervisor",
    "SupervisorDecision",
    "SupervisorOrchestrator",
    "SupervisorTurnResult",
    "USE_LLM_SUPERVISOR",
    "merge_state_delta",
    "normalize_short_answer",
    "should_use_supervisor",
    "try_parse_pending_answer",
]
