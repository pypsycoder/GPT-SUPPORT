"""Deterministic expert agents for the supervisor MVP."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.llm.supervisor.models import ContentBlock, CurrentState, ExpertResult, ExpertTask


def _block(kind: str, text: str, dedupe_key: str) -> ContentBlock:
    return {"kind": kind, "text": text, "dedupe_key": dedupe_key}


class BaseExpertAgent(ABC):
    agent_name: str

    @abstractmethod
    def run(self, task: ExpertTask) -> ExpertResult:
        raise NotImplementedError


class EmotionalSupportAgent(BaseExpertAgent):
    agent_name = "emotional_support"

    def run(self, task: ExpertTask) -> ExpertResult:
        state = CurrentState.from_dict(task.state_snapshot)
        blocks = [
            _block("validation", "Похоже, сейчас тебе правда непросто.", "support_validation"),
            _block(
                "explanation",
                "Такая реакция понятна, особенно когда много напряжения и неопределенности.",
                "support_normalization",
            ),
        ]
        if "before_dialysis" in state.risk_flags:
            blocks.append(
                _block(
                    "action",
                    "Сейчас лучше не пытаться решить все сразу, а немного сузить фокус до ближайшего часа.",
                    "support_before_dialysis_action",
                )
            )
        return ExpertResult(
            agent_name=self.agent_name,
            content_blocks=blocks,
            state_delta={"signals_add": ["support_provided"]},
            confidence=0.87,
        )


class EducationAgent(BaseExpertAgent):
    agent_name = "education"

    def run(self, task: ExpertTask) -> ExpertResult:
        state = CurrentState.from_dict(task.state_snapshot)
        if state.domain == "health":
            explanation = "Когда состояние связано с лечением или симптомами, тревога часто усиливается из-за нехватки понятной опоры."
        elif state.domain == "daily_routine":
            explanation = "Когда сбивается повседневный ритм, самочувствие и ощущение контроля обычно проседают вместе."
        else:
            explanation = "Когда неясно, что именно происходит, мозг часто держит напряжение дольше обычного."
        return ExpertResult(
            agent_name=self.agent_name,
            content_blocks=[_block("explanation", explanation, "education_explanation")],
            state_delta={"signals_add": ["education_provided"]},
            confidence=0.81,
        )


class PlanningAgent(BaseExpertAgent):
    agent_name = "planning"

    def run(self, task: ExpertTask) -> ExpertResult:
        state = CurrentState.from_dict(task.state_snapshot)
        if "before_dialysis" in state.risk_flags:
            action_text = "На ближайший шаг выбери что-то одно: сесть поудобнее, сделать 3 спокойных выдоха или коротко написать, что пугает сильнее всего."
        elif state.domain == "daily_routine":
            action_text = "Сделай один минимальный шаг на ближайшие 10 минут, а не план на весь день."
        else:
            action_text = "Сейчас полезнее выбрать один конкретный следующий шаг, а не пытаться решить все сразу."
        return ExpertResult(
            agent_name=self.agent_name,
            content_blocks=[_block("action", action_text, "planning_next_step")],
            state_delta={"signals_add": ["plan_provided"]},
            confidence=0.84,
        )


def _wants_support(state: CurrentState) -> bool:
    return state.intent == "support" or any(signal in state.signals for signal in {"distress", "emotional_pain"})


def _wants_plan(state: CurrentState) -> bool:
    return state.intent == "plan" or "needs_plan" in state.signals


def _wants_education(state: CurrentState) -> bool:
    return state.intent == "inform" or "needs_explanation" in state.signals


def select_agents(current_state: CurrentState) -> list[str]:
    selected: list[str] = []
    if _wants_support(current_state):
        selected.append("emotional_support")
    if _wants_plan(current_state):
        selected.append("planning")
    if _wants_education(current_state):
        selected.append("education")
    if not selected:
        selected.append("emotional_support")
    return selected[:2]


def build_agent(agent_name: str) -> BaseExpertAgent:
    if agent_name == "emotional_support":
        return EmotionalSupportAgent()
    if agent_name == "planning":
        return PlanningAgent()
    if agent_name == "education":
        return EducationAgent()
    raise ValueError(f"Unknown agent: {agent_name}")
