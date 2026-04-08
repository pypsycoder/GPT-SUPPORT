"""Stateful MVP supervisor-orchestrator."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.llm.supervisor.classification import classify_message
from app.llm.supervisor.experts import build_agent, select_agents
from app.llm.supervisor.models import CurrentState, ExpertTask, PendingQuestion, SupervisorTurnResult
from app.llm.supervisor.short_answers import try_parse_pending_answer
from app.llm.supervisor.state_merge import merge_state_delta
from app.llm.supervisor.synthesizer import ResponseSynthesizer


class SupervisorOrchestrator:
    """Main deterministic stateful flow."""

    def __init__(self) -> None:
        self._synthesizer = ResponseSynthesizer()

    def handle_message(self, user_message: str, current_state: CurrentState | dict[str, Any] | None) -> SupervisorTurnResult:
        state = current_state if isinstance(current_state, CurrentState) else CurrentState.from_dict(current_state)
        original_state = CurrentState.from_dict(state.to_dict())
        diagnostics: dict[str, Any] = {}

        parsed_pending = None
        if state.pending_question:
            parsed_pending = try_parse_pending_answer(user_message, state.pending_question)

        if parsed_pending:
            message_type = "short_answer"
            base_delta = self._build_slot_fill_delta(state, parsed_pending)
            working_state = merge_state_delta(state, base_delta)
            diagnostics["pending_answer"] = parsed_pending
        else:
            classification = classify_message(user_message, state)
            message_type = classification["message_type"]
            diagnostics["classification"] = classification

            if message_type == "meta_message":
                delta = {"signals_add": ["meta_reply_seen"]}
                updated_state = merge_state_delta(state, delta)
                return SupervisorTurnResult(
                    reply="Пожалуйста. Если хочешь, можем продолжить и разобрать это дальше.",
                    state_delta=delta,
                    updated_state=updated_state,
                    message_type=message_type,
                    selected_agents=[],
                    used_pending_answer=False,
                    needs_clarification=False,
                    diagnostics=diagnostics,
                )

            base_delta = self._build_classification_delta(classification, state)
            working_state = merge_state_delta(state, base_delta)

        clarification = self._build_clarification_if_needed(working_state)
        if clarification is not None:
            clarification_delta = {
                "pending_question_set": clarification.to_dict(),
                "needs_clarification": True,
            }
            full_delta = self._combine_deltas(base_delta, clarification_delta)
            updated_state = merge_state_delta(original_state, full_delta)
            return SupervisorTurnResult(
                reply=clarification.question_text,
                state_delta=full_delta,
                updated_state=updated_state,
                message_type=message_type,
                selected_agents=[],
                used_pending_answer=parsed_pending is not None,
                needs_clarification=True,
                diagnostics=diagnostics,
            )

        selected_agents = select_agents(working_state)
        content_blocks: list[dict[str, str]] = []
        combined_delta = deepcopy(base_delta)

        for agent_name in selected_agents:
            task = ExpertTask(
                agent_name=agent_name,
                goal=working_state.goal,
                domain=working_state.domain,
                intent=working_state.intent,
                state_snapshot=working_state.to_dict(),
            )
            result = build_agent(agent_name).run(task)
            content_blocks.extend(result.content_blocks)
            combined_delta = self._combine_deltas(combined_delta, result.state_delta)
            working_state = merge_state_delta(working_state, result.state_delta)

        combined_delta = self._combine_deltas(
            combined_delta,
            {
                "last_selected_agents_set": selected_agents,
                "needs_clarification": False,
                "pending_question_set": None,
            },
        )
        updated_state = merge_state_delta(original_state, combined_delta)
        reply = self._synthesizer.synthesize(content_blocks)
        diagnostics["selected_agents"] = selected_agents

        return SupervisorTurnResult(
            reply=reply,
            state_delta=combined_delta,
            updated_state=updated_state,
            message_type=message_type,
            selected_agents=selected_agents,
            used_pending_answer=parsed_pending is not None,
            needs_clarification=False,
            diagnostics=diagnostics,
        )

    def _build_slot_fill_delta(self, state: CurrentState, parsed_pending: dict[str, Any]) -> dict[str, Any]:
        slots = dict(state.slots)
        slots[parsed_pending["slot_name"]] = parsed_pending["slot_value"]
        delta: dict[str, Any] = {
            "slots_set": slots,
            "pending_question_set": None,
            "needs_clarification": False,
        }
        if parsed_pending["slot_name"] == "goal":
            slot_value = parsed_pending["slot_value"]
            delta["goal"] = slot_value if isinstance(slot_value, str) else str(slot_value)
        return delta

    def _build_classification_delta(self, classification: dict[str, Any], state: CurrentState) -> dict[str, Any]:
        goal = classification["goal"] or state.goal
        signals = list(classification["signals"])
        if classification["message_type"] == "correction":
            signals.append("correction")
        return {
            "domain": classification["domain"],
            "intent": classification["intent"],
            "goal": goal,
            "risk_flags_add": classification["risk_flags"],
            "signals_add": signals,
            "facts_add": classification["facts"],
        }

    def _build_clarification_if_needed(self, state: CurrentState) -> PendingQuestion | None:
        if "distress" in state.risk_flags and "distress_level" not in state.slots:
            return PendingQuestion(
                slot_name="distress_level",
                question_text="Насколько это тяжело сейчас по шкале от 0 до 10?",
                expected_kind="scale_0_10",
                attempts=(state.pending_question.attempts + 1) if state.pending_question else 1,
            )
        if not state.goal:
            if state.intent == "inform":
                return PendingQuestion(
                    slot_name="goal",
                    question_text="Что именно ты хочешь понять или прояснить?",
                    expected_kind="free_text",
                    attempts=(state.pending_question.attempts + 1) if state.pending_question else 1,
                )
            if state.intent == "plan":
                return PendingQuestion(
                    slot_name="goal",
                    question_text="Какой следующий шаг тебе нужен прямо сейчас?",
                    expected_kind="free_text",
                    attempts=(state.pending_question.attempts + 1) if state.pending_question else 1,
                )
            return PendingQuestion(
                slot_name="goal",
                question_text="Что сейчас беспокоит тебя больше всего?",
                expected_kind="free_text",
                attempts=(state.pending_question.attempts + 1) if state.pending_question else 1,
            )
        return None

    def _combine_deltas(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        combined = deepcopy(left)
        for key, value in right.items():
            if key.endswith("_add"):
                existing = list(combined.get(key) or [])
                for item in list(value or []):
                    if item not in existing:
                        existing.append(item)
                combined[key] = existing
                continue
            combined[key] = value
        return combined
