"""JSON-friendly models for the stateful supervisor MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ContentBlock = dict[str, str]


# PendingQuestion
@dataclass(slots=True)
class PendingQuestion:
    slot_name: str
    question_text: str
    expected_kind: str
    attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "PendingQuestion | None":
        if not payload:
            return None
        return cls(
            slot_name=str(payload.get("slot_name") or "").strip(),
            question_text=str(payload.get("question_text") or "").strip(),
            expected_kind=str(payload.get("expected_kind") or "free_text").strip() or "free_text",
            attempts=int(payload.get("attempts") or 0),
        )


# CurrentState
@dataclass(slots=True)
class CurrentState:
    domain: str | None = None
    intent: str | None = None
    goal: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    risk_flags: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    pending_question: PendingQuestion | None = None
    last_selected_agents: list[str] = field(default_factory=list)
    needs_clarification: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "intent": self.intent,
            "goal": self.goal,
            "slots": dict(self.slots),
            "risk_flags": list(self.risk_flags),
            "signals": list(self.signals),
            "facts": list(self.facts),
            "pending_question": self.pending_question.to_dict() if self.pending_question else None,
            "last_selected_agents": list(self.last_selected_agents),
            "needs_clarification": bool(self.needs_clarification),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "CurrentState":
        payload = payload or {}
        return cls(
            domain=str(payload.get("domain")).strip() if payload.get("domain") is not None else None,
            intent=str(payload.get("intent")).strip() if payload.get("intent") is not None else None,
            goal=str(payload.get("goal")).strip() if payload.get("goal") is not None else None,
            slots=dict(payload.get("slots") or {}),
            risk_flags=[str(item) for item in (payload.get("risk_flags") or []) if str(item).strip()],
            signals=[str(item) for item in (payload.get("signals") or []) if str(item).strip()],
            facts=[str(item) for item in (payload.get("facts") or []) if str(item).strip()],
            pending_question=PendingQuestion.from_dict(payload.get("pending_question")),
            last_selected_agents=[
                str(item) for item in (payload.get("last_selected_agents") or []) if str(item).strip()
            ],
            needs_clarification=bool(payload.get("needs_clarification")),
        )


# ExpertTask
@dataclass(slots=True)
class ExpertTask:
    agent_name: str
    goal: str | None
    domain: str | None
    intent: str | None
    state_snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExpertTask":
        return cls(
            agent_name=str(payload.get("agent_name") or "").strip(),
            goal=str(payload.get("goal")).strip() if payload.get("goal") is not None else None,
            domain=str(payload.get("domain")).strip() if payload.get("domain") is not None else None,
            intent=str(payload.get("intent")).strip() if payload.get("intent") is not None else None,
            state_snapshot=dict(payload.get("state_snapshot") or {}),
        )


# ExpertResult
@dataclass(slots=True)
class ExpertResult:
    agent_name: str
    content_blocks: list[ContentBlock] = field(default_factory=list)
    state_delta: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "content_blocks": [dict(block) for block in self.content_blocks],
            "state_delta": dict(self.state_delta),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExpertResult":
        return cls(
            agent_name=str(payload.get("agent_name") or "").strip(),
            content_blocks=[dict(item) for item in (payload.get("content_blocks") or [])],
            state_delta=dict(payload.get("state_delta") or {}),
            confidence=float(payload.get("confidence") or 0.0),
        )


# SupervisorTurnResult
@dataclass(slots=True)
class SupervisorTurnResult:
    reply: str
    state_delta: dict[str, Any]
    updated_state: CurrentState
    message_type: str
    selected_agents: list[str] = field(default_factory=list)
    used_pending_answer: bool = False
    needs_clarification: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "state_delta": dict(self.state_delta),
            "updated_state": self.updated_state.to_dict(),
            "message_type": self.message_type,
            "selected_agents": list(self.selected_agents),
            "used_pending_answer": self.used_pending_answer,
            "needs_clarification": self.needs_clarification,
            "diagnostics": dict(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SupervisorTurnResult":
        return cls(
            reply=str(payload.get("reply") or "").strip(),
            state_delta=dict(payload.get("state_delta") or {}),
            updated_state=CurrentState.from_dict(payload.get("updated_state")),
            message_type=str(payload.get("message_type") or "full_message").strip(),
            selected_agents=[str(item) for item in (payload.get("selected_agents") or []) if str(item).strip()],
            used_pending_answer=bool(payload.get("used_pending_answer")),
            needs_clarification=bool(payload.get("needs_clarification")),
            diagnostics=dict(payload.get("diagnostics") or {}),
        )
