"""Minimal Graph v2 models for supervisor intake/delegation/expert flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.llm.supervisor.models import CurrentState


class BinaryChoice(StrEnum):
    YES = "да"
    NO = "нет"

    @classmethod
    def parse(cls, value: str, *, field_name: str) -> "BinaryChoice":
        normalized = str(value or "").strip().lower()
        if normalized == cls.YES.value:
            return cls.YES
        if normalized == cls.NO.value:
            return cls.NO
        raise ValueError(f"{field_name} must be да or нет")


class DelegationExpert(StrEnum):
    EMOTIONAL_SUPPORT = "эмоциональная_поддержка"

    @classmethod
    def parse(cls, value: str) -> "DelegationExpert":
        return cls(str(value or "").strip())


class ValidationDecision(StrEnum):
    ACCEPT = "принять"
    RETRY = "повторить_анализ"
    REJECT = "отклонить"


class ExecutionKind(StrEnum):
    ASK = "уточнение"
    DELEGATE = "делегация"
    FINISH = "завершение"


@dataclass(slots=True)
class IntakeCard:
    problem: str
    context: str
    needs_clarification: BinaryChoice
    question: str
    ready_to_delegate: BinaryChoice
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem": self.problem,
            "context": self.context,
            "needs_clarification": self.needs_clarification.value,
            "question": self.question,
            "ready_to_delegate": self.ready_to_delegate.value,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "IntakeCard | None":
        if not payload:
            return None
        return cls(
            problem=str(payload.get("problem") or "").strip(),
            context=str(payload.get("context") or "").strip(),
            needs_clarification=BinaryChoice.parse(
                str(payload.get("needs_clarification") or "").strip(),
                field_name="Нужно уточнение",
            ),
            question=str(payload.get("question") or "").strip(),
            ready_to_delegate=BinaryChoice.parse(
                str(payload.get("ready_to_delegate") or "").strip(),
                field_name="Готово к передаче",
            ),
            rationale=str(payload.get("rationale") or "").strip(),
        )


@dataclass(slots=True)
class DelegationCard:
    expert: DelegationExpert
    task: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert": self.expert.value,
            "task": self.task,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "DelegationCard | None":
        if not payload:
            return None
        return cls(
            expert=DelegationExpert.parse(str(payload.get("expert") or "").strip()),
            task=str(payload.get("task") or "").strip(),
            rationale=str(payload.get("rationale") or "").strip(),
        )


@dataclass(slots=True)
class EmotionalExpertCard:
    support: str
    step_now: str
    follow_up: str
    needs_more_info: BinaryChoice
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "support": self.support,
            "step_now": self.step_now,
            "follow_up": self.follow_up,
            "needs_more_info": self.needs_more_info.value,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "EmotionalExpertCard | None":
        if not payload:
            return None
        return cls(
            support=str(payload.get("support") or "").strip(),
            step_now=str(payload.get("step_now") or "").strip(),
            follow_up=str(payload.get("follow_up") or "").strip(),
            needs_more_info=BinaryChoice.parse(
                str(payload.get("needs_more_info") or "").strip(),
                field_name="Нужно ли уточнение",
            ),
            rationale=str(payload.get("rationale") or "").strip(),
        )


@dataclass(slots=True)
class FirstModuleInput:
    user_message: str
    current_state: CurrentState
    message_type: str
    model_tier: str
    strict_model_tier: bool = False


@dataclass(slots=True)
class FirstModuleState:
    user_message: str
    current_state: CurrentState
    message_type: str
    model_tier: str
    strict_model_tier: bool = False
    intake_card: IntakeCard | None = None
    delegation_card: DelegationCard | None = None
    expert_card: EmotionalExpertCard | None = None
    intake_validation: ValidationDecision | None = None
    delegation_validation: ValidationDecision | None = None
    intake_error: str | None = None
    delegation_error: str | None = None
    execution_kind: ExecutionKind | None = None
    user_question: str | None = None
    final_reply: str | None = None
    needs_clarification: bool = False
    selected_agents: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_latency_ms: int = 0
    account_ids: list[str] = field(default_factory=list)
    actual_model_tiers: list[str] = field(default_factory=list)

    @classmethod
    def from_input(cls, payload: FirstModuleInput) -> "FirstModuleState":
        return cls(
            user_message=payload.user_message,
            current_state=CurrentState.from_dict(payload.current_state.to_dict()),
            message_type=payload.message_type,
            model_tier=payload.model_tier,
            strict_model_tier=payload.strict_model_tier,
        )

    def register_llm_call(
        self,
        *,
        account_id: str,
        actual_model_tier: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
    ) -> None:
        self.total_tokens_input += int(tokens_in or 0)
        self.total_tokens_output += int(tokens_out or 0)
        self.total_latency_ms += int(latency_ms or 0)
        if account_id:
            self.account_ids.append(str(account_id))
        if actual_model_tier:
            self.actual_model_tiers.append(str(actual_model_tier))

    def to_graph_dict(self) -> dict[str, Any]:
        return {
            "user_message": self.user_message,
            "current_state": self.current_state.to_dict(),
            "message_type": self.message_type,
            "model_tier": self.model_tier,
            "strict_model_tier": self.strict_model_tier,
            "intake_card": self.intake_card.to_dict() if self.intake_card else None,
            "delegation_card": self.delegation_card.to_dict() if self.delegation_card else None,
            "expert_card": self.expert_card.to_dict() if self.expert_card else None,
            "intake_validation": self.intake_validation.value if self.intake_validation else None,
            "delegation_validation": self.delegation_validation.value if self.delegation_validation else None,
            "intake_error": self.intake_error,
            "delegation_error": self.delegation_error,
            "execution_kind": self.execution_kind.value if self.execution_kind else None,
            "user_question": self.user_question,
            "final_reply": self.final_reply,
            "needs_clarification": self.needs_clarification,
            "selected_agents": list(self.selected_agents),
            "diagnostics": dict(self.diagnostics),
            "total_tokens_input": self.total_tokens_input,
            "total_tokens_output": self.total_tokens_output,
            "total_latency_ms": self.total_latency_ms,
            "account_ids": list(self.account_ids),
            "actual_model_tiers": list(self.actual_model_tiers),
        }

    @classmethod
    def from_graph_dict(cls, payload: dict[str, Any]) -> "FirstModuleState":
        intake_validation_raw = payload.get("intake_validation")
        delegation_validation_raw = payload.get("delegation_validation")
        execution_kind_raw = payload.get("execution_kind")
        return cls(
            user_message=str(payload.get("user_message") or ""),
            current_state=CurrentState.from_dict(payload.get("current_state")),
            message_type=str(payload.get("message_type") or "full_message"),
            model_tier=str(payload.get("model_tier") or "lite"),
            strict_model_tier=bool(payload.get("strict_model_tier")),
            intake_card=IntakeCard.from_dict(payload.get("intake_card")),
            delegation_card=DelegationCard.from_dict(payload.get("delegation_card")),
            expert_card=EmotionalExpertCard.from_dict(payload.get("expert_card")),
            intake_validation=ValidationDecision(intake_validation_raw) if intake_validation_raw else None,
            delegation_validation=ValidationDecision(delegation_validation_raw) if delegation_validation_raw else None,
            intake_error=str(payload.get("intake_error")).strip() if payload.get("intake_error") is not None else None,
            delegation_error=(
                str(payload.get("delegation_error")).strip()
                if payload.get("delegation_error") is not None
                else None
            ),
            execution_kind=ExecutionKind(execution_kind_raw) if execution_kind_raw else None,
            user_question=str(payload.get("user_question")).strip() if payload.get("user_question") is not None else None,
            final_reply=str(payload.get("final_reply")).strip() if payload.get("final_reply") is not None else None,
            needs_clarification=bool(payload.get("needs_clarification")),
            selected_agents=[str(item) for item in (payload.get("selected_agents") or []) if str(item).strip()],
            diagnostics=dict(payload.get("diagnostics") or {}),
            total_tokens_input=int(payload.get("total_tokens_input") or 0),
            total_tokens_output=int(payload.get("total_tokens_output") or 0),
            total_latency_ms=int(payload.get("total_latency_ms") or 0),
            account_ids=[str(item) for item in (payload.get("account_ids") or []) if str(item).strip()],
            actual_model_tiers=[
                str(item) for item in (payload.get("actual_model_tiers") or []) if str(item).strip()
            ],
        )
