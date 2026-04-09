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

    MAX_CLARIFICATION_STREAK = 5

    def __init__(self) -> None:
        self._synthesizer = ResponseSynthesizer()

    def handle_message(
        self,
        user_message: str,
        current_state: CurrentState | dict[str, Any] | None,
        goal_resolution: dict[str, Any] | None = None,
    ) -> SupervisorTurnResult:
        state = current_state if isinstance(current_state, CurrentState) else CurrentState.from_dict(current_state)
        original_state = CurrentState.from_dict(state.to_dict())
        diagnostics: dict[str, Any] = {}
        if goal_resolution is not None:
            diagnostics["goal_analysis"] = dict(goal_resolution)

        parsed_pending = None
        if state.pending_question:
            parsed_pending = try_parse_pending_answer(user_message, state.pending_question)

        if parsed_pending:
            message_type = "short_answer"
            base_delta = self._build_slot_fill_delta(state, parsed_pending, goal_resolution)
            working_state = merge_state_delta(state, base_delta)
            diagnostics["pending_answer"] = parsed_pending
        else:
            classification = classify_message(user_message, state)
            message_type = classification["message_type"]
            diagnostics["classification"] = classification

            if message_type == "meta_message":
                delta = {
                    "signals_add": ["meta_reply_seen"],
                    "clarification_streak": 0,
                    "last_clarification_reason_set": None,
                }
                updated_state = merge_state_delta(state, delta)
                return SupervisorTurnResult(
                    reply="Пожалуйста. Если хочешь, можем спокойно продолжить и разобрать это дальше.",
                    state_delta=delta,
                    updated_state=updated_state,
                    message_type=message_type,
                    selected_agents=[],
                    used_pending_answer=False,
                    needs_clarification=False,
                    diagnostics=diagnostics,
                )

            base_delta = self._build_classification_delta(classification, state, goal_resolution)
            working_state = merge_state_delta(state, base_delta)

        clarification, clarification_state_delta, clarification_reason = self._build_clarification_if_needed(
            state=working_state,
            previous_state=state,
            previous_attempts=(state.pending_question.attempts if state.pending_question else 0),
            goal_resolution=goal_resolution,
        )
        if clarification is not None:
            response_mode = self._decide_response_mode(working_state, goal_resolution, clarify_active=True)
            clarification_delta = {
                "pending_question_set": clarification.to_dict(),
                "needs_clarification": True,
                "clarification_streak": state.clarification_streak + 1,
                "last_clarification_reason": clarification_reason,
                **clarification_state_delta,
            }
            full_delta = self._combine_deltas(base_delta, clarification_delta)
            updated_state = merge_state_delta(original_state, full_delta)
            diagnostics["clarification_gate"] = {
                "reason": clarification_reason,
                "forced_by_cap": False,
            }
            diagnostics["response_mode"] = response_mode
            diagnostics["context_sufficiency"] = self._build_context_sufficiency(goal_resolution)
            return SupervisorTurnResult(
                reply=self._build_clarification_reply(response_mode, clarification),
                state_delta=full_delta,
                updated_state=updated_state,
                message_type=message_type,
                selected_agents=[],
                used_pending_answer=parsed_pending is not None,
                needs_clarification=True,
                diagnostics=diagnostics,
            )

        response_mode = self._decide_response_mode(working_state, goal_resolution, clarify_active=False)
        if goal_resolution and goal_resolution.get("needs_clarification") and state.clarification_streak >= self.MAX_CLARIFICATION_STREAK:
            diagnostics["clarification_gate"] = {
                "reason": goal_resolution.get("clarification_reason") or goal_resolution.get("reason"),
                "forced_by_cap": True,
                "cap": self.MAX_CLARIFICATION_STREAK,
            }
            response_mode = self._decide_response_mode(working_state, goal_resolution, clarify_active=False, forced_help=True)

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
                "clarification_streak": 0,
                "last_clarification_reason_set": None,
            },
        )
        updated_state = merge_state_delta(original_state, combined_delta)
        reply = self._synthesizer.synthesize(content_blocks)
        diagnostics["selected_agents"] = selected_agents
        diagnostics["response_mode"] = response_mode
        diagnostics["context_sufficiency"] = self._build_context_sufficiency(goal_resolution)

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

    def _build_slot_fill_delta(
        self,
        state: CurrentState,
        parsed_pending: dict[str, Any],
        goal_resolution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        slots = dict(state.slots)
        delta: dict[str, Any] = {
            "pending_question_set": None,
            "needs_clarification": False,
        }

        if parsed_pending["slot_name"] == "goal":
            raw_value = parsed_pending["slot_value"]
            slots["goal_raw"] = raw_value
            if goal_resolution is not None:
                resolved_goal = goal_resolution.get("goal")
                slots["goal"] = resolved_goal or raw_value
                delta["goal_set"] = resolved_goal
                delta["last_goal_status"] = goal_resolution.get("goal_status") or goal_resolution.get("reason")
            else:
                slots["goal"] = raw_value
                delta["goal_set"] = raw_value if isinstance(raw_value, str) else str(raw_value)
        else:
            slots[parsed_pending["slot_name"]] = parsed_pending["slot_value"]

        delta["slots_set"] = slots
        return delta

    def _build_classification_delta(
        self,
        classification: dict[str, Any],
        state: CurrentState,
        goal_resolution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        analysis = goal_resolution or {}
        signals = list(classification["signals"])
        if classification["message_type"] == "correction":
            signals.append("correction")
        risk_flags = list(classification["risk_flags"])
        facts = list(classification["facts"])

        state_hints = dict(analysis.get("state_hints") or {})
        for item in list(state_hints.get("signals") or []):
            if item not in signals:
                signals.append(item)
        for item in list(state_hints.get("risk_flags") or []):
            if item not in risk_flags:
                risk_flags.append(item)
        for item in list(state_hints.get("facts") or []):
            if item not in facts:
                facts.append(item)

        domain = str(state_hints.get("domain") or classification["domain"]).strip() or classification["domain"]
        intent = str(state_hints.get("intent") or classification["intent"]).strip() or classification["intent"]

        delta: dict[str, Any] = {
            "domain": domain,
            "intent": intent,
            "goal_set": analysis.get("goal") if analysis else (classification["goal"] or state.goal),
            "risk_flags_add": risk_flags,
            "signals_add": signals,
            "facts_add": facts,
        }
        if analysis:
            delta["last_goal_status"] = analysis.get("goal_status") or analysis.get("reason")
            if "clarification_reason" in analysis:
                delta["last_clarification_reason_set"] = analysis.get("clarification_reason")
        return delta

    def _decide_response_mode(
        self,
        state: CurrentState,
        goal_resolution: dict[str, Any] | None,
        *,
        clarify_active: bool,
        forced_help: bool = False,
    ) -> str:
        analysis = goal_resolution or {}
        if clarify_active and not forced_help:
            if (analysis.get("goal_status") == "generic_distress") or (
                analysis.get("clarification_reason") == "generic_distress"
            ):
                return "hybrid_clarify"
            return "clarify_only"

        if state.intent == "plan":
            return "direct_plan"
        return "direct_support"

    def _build_context_sufficiency(self, goal_resolution: dict[str, Any] | None) -> dict[str, bool | None]:
        analysis = goal_resolution or {}
        return {
            "support": analysis.get("enough_context_for_support"),
            "plan": analysis.get("enough_context_for_plan"),
        }

    def _build_clarification_reply(self, response_mode: str, clarification: PendingQuestion) -> str:
        if response_mode != "hybrid_clarify":
            return clarification.question_text
        return (
            "Сейчас это правда может сильно давить. "
            "Попробуй на пару дыханий чуть замедлиться и сделать выдох длиннее вдоха. "
            f"{clarification.question_text}"
        )

    def _default_clarification_question(self, state: CurrentState, attempts: int) -> PendingQuestion:
        if state.intent == "inform":
            return PendingQuestion(
                slot_name="goal",
                question_text="Что именно ты хочешь понять или прояснить?",
                expected_kind="free_text",
                attempts=attempts,
                reason="context_missing",
            )
        if state.intent == "plan":
            return PendingQuestion(
                slot_name="goal",
                question_text="Какой следующий шаг тебе нужен прямо сейчас?",
                expected_kind="free_text",
                attempts=attempts,
                reason="context_missing",
            )
        return PendingQuestion(
            slot_name="goal",
            question_text="Что сейчас беспокоит тебя больше всего?",
            expected_kind="free_text",
            attempts=attempts,
            reason="context_missing",
        )

    def _build_clarification_if_needed(
        self,
        state: CurrentState,
        previous_state: CurrentState,
        previous_attempts: int = 0,
        goal_resolution: dict[str, Any] | None = None,
    ) -> tuple[PendingQuestion | None, dict[str, Any], str | None]:
        analysis = goal_resolution or {}
        needs_clarification = bool(analysis.get("needs_clarification"))
        clarification_reason = (
            str(analysis.get("clarification_reason") or analysis.get("reason") or "").strip() or None
        )

        if not analysis:
            if state.goal:
                return None, {}, None
            pending = self._default_clarification_question(state, previous_attempts + 1)
            return pending, {}, pending.reason

        if not needs_clarification:
            return None, {}, clarification_reason

        if previous_state.clarification_streak >= self.MAX_CLARIFICATION_STREAK:
            return None, {}, clarification_reason

        question_text = str(analysis.get("clarification_question") or "").strip()
        if not question_text:
            raise ValueError("goal analysis requested clarification without clarification_question")

        pending = PendingQuestion(
            slot_name="goal",
            question_text=question_text,
            expected_kind="free_text",
            attempts=previous_attempts + 1,
            reason=clarification_reason,
        )
        return pending, {}, clarification_reason

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
