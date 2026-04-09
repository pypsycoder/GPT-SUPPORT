"""
Supervisor Stage - stateful MVP orchestrator.

Runs after Classification and becomes the main decision-making path for
ordinary text requests while keeping pipeline compatibility intact.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.llm.errors import LLMResponseError
from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.pool import pool
from app.llm.router import RequestType
from app.llm.supervisor import CurrentState, SupervisorOrchestrator

logger = logging.getLogger("gpt-support-llm.pipeline.supervisor")

_MAX_ANALYSIS_ATTEMPTS = 3
_GOAL_STATUS_VALUES = {"resolved", "generic_distress", "context_missing", "unclear", "correction"}
_REQUIRED_ANALYSIS_FIELDS = {
    "goal",
    "goal_status",
    "needs_clarification",
    "clarification_question",
    "clarification_reason",
    "enough_context_for_support",
    "enough_context_for_plan",
}
_OPTIONAL_ANALYSIS_FIELDS = {
    "state_hints.signals",
    "state_hints.risk_flags",
    "state_hints.facts",
    "state_hints.domain",
    "state_hints.intent",
}
_BOOLEAN_VALUES = {"true": True, "false": False}
_ANCHOR_KEYWORDS = (
    "диализ",
    "гемодиализ",
    "процедур",
    "сеанс",
    "таблет",
    "лекар",
    "пропустил",
    "не выпил",
    "давлен",
    "самочувств",
    "тошнит",
    "слабост",
    "боль",
    "завтра",
    "сегодня",
    "перед",
    "жду",
    "скоро",
)
_ANCHOR_CATEGORY_KEYWORDS = {
    "dialysis": ("диализ", "гемодиализ", "процедур", "сеанс"),
    "medication": ("таблет", "лекар", "пропустил", "не выпил"),
    "pressure": ("давлен",),
    "physical": ("самочувств", "тошнит", "слабост", "боль"),
}
_SIDE_DETAIL_PATTERNS = (
    "как часто",
    "с какой частот",
    "сколько раз",
    "когда у тебя",
    "когда у вас",
    "как давно",
    "сколько длится",
    "сколько по времени",
    "в какой день",
)
_ANCHOR_FOCUS_PATTERNS = (
    "что именно в этом",
    "что в этом",
    "что именно тебя",
    "что именно вас",
    "что именно тревожит",
    "что больше всего пугает",
    "что сильнее всего тревожит",
    "что в предстоящем",
    "что в этом для тебя",
    "что в этом для вас",
)


# _build_memory_reads
def _build_memory_reads(context_data: dict) -> dict[str, object]:
    st_items = list(context_data.get("st_memory") or [])
    lt_items = list(context_data.get("lt_memory") or [])
    return {
        "st_items": st_items,
        "lt_items": lt_items,
        "st_count": len(st_items),
        "lt_count": len(lt_items),
    }


# _needs_support_grounding
def _needs_support_grounding(context: PipelineContext) -> bool:
    turn = context.supervisor_turn
    if turn is None:
        return False
    if any(agent in {"emotional_support", "planning"} for agent in (turn.selected_agents or [])):
        return True
    state = dict(context.supervisor_state or {})
    signals = set(str(item) for item in (state.get("signals") or []))
    return bool(signals.intersection({"distress", "emotional_pain", "dialysis_context"}))


# _strip_code_fence
def _strip_code_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


# _parse_field_block
def _parse_field_block(text: str) -> dict[str, str]:
    cleaned = _strip_code_fence(text)
    if not cleaned:
        raise ValueError("goal analysis returned empty field block")

    fields: dict[str, str] = {}
    for line_number, raw_line in enumerate(cleaned.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"goal analysis line {line_number} is not a field entry")
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"goal analysis line {line_number} has empty field name")
        if key in fields:
            raise ValueError(f"goal analysis contains duplicate field: {key}")
        fields[key] = value.strip()

    missing = sorted(_REQUIRED_ANALYSIS_FIELDS.difference(fields))
    if missing:
        raise ValueError(f"goal analysis missing required fields: {', '.join(missing)}")

    allowed_fields = _REQUIRED_ANALYSIS_FIELDS | _OPTIONAL_ANALYSIS_FIELDS
    unknown = sorted(set(fields).difference(allowed_fields))
    if unknown:
        raise ValueError(f"goal analysis has unknown fields: {', '.join(unknown)}")

    return fields


# _parse_nullable_text
def _parse_nullable_text(value: str) -> str | None:
    text = str(value or "").strip()
    if text.lower() in {"", "null", "none"}:
        return None
    return text


# _parse_boolean_field
def _parse_boolean_field(value: str, field_name: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized not in _BOOLEAN_VALUES:
        raise ValueError(f"{field_name} must be true or false")
    return _BOOLEAN_VALUES[normalized]


# _parse_csv_list
def _parse_csv_list(value: str) -> list[str]:
    text = str(value or "").strip()
    if text.lower() in {"", "null", "none"}:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


# _normalize_anchor_text
def _normalize_anchor_text(value: str | None) -> str:
    return str(value or "").strip().lower().replace("ё", "е")


# _contains_anchor
def _contains_anchor(text: str | None) -> bool:
    normalized = _normalize_anchor_text(text)
    return any(keyword in normalized for keyword in _ANCHOR_KEYWORDS)


# _looks_anchored_followup
def _looks_anchored_followup(user_message: str, state: CurrentState) -> bool:
    if _contains_anchor(user_message):
        return True
    pending = state.pending_question
    if pending and pending.slot_name == "goal" and _contains_anchor(user_message):
        return True
    return False


# _anchor_categories
def _anchor_categories(*texts: str | None) -> set[str]:
    categories: set[str] = set()
    for text in texts:
        normalized = _normalize_anchor_text(text)
        if not normalized:
            continue
        for category, keywords in _ANCHOR_CATEGORY_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                categories.add(category)
    return categories


# _question_mentions_anchor_context
def _question_mentions_anchor_context(question: str, categories: set[str]) -> bool:
    normalized = _normalize_anchor_text(question)
    if any(pattern in normalized for pattern in _ANCHOR_FOCUS_PATTERNS):
        return True
    for category in categories:
        keywords = _ANCHOR_CATEGORY_KEYWORDS.get(category) or ()
        if any(keyword in normalized for keyword in keywords):
            return True
    return False


# _question_is_side_detail
def _question_is_side_detail(question: str) -> bool:
    normalized = _normalize_anchor_text(question)
    return any(pattern in normalized for pattern in _SIDE_DETAIL_PATTERNS)


# _validate_anchor_consistency
def _validate_anchor_consistency(
    *,
    user_message: str,
    state: CurrentState,
    goal: str | None,
    goal_status: str,
) -> None:
    if goal_status != "generic_distress":
        return
    if _contains_anchor(goal) or _looks_anchored_followup(user_message, state):
        raise ValueError("anchored follow-up cannot be labeled generic_distress")


# _validate_clarification_question_quality
def _validate_clarification_question_quality(
    *,
    user_message: str,
    state: CurrentState,
    goal: str | None,
    needs_clarification: bool,
    clarification_question: str | None,
) -> None:
    if not needs_clarification or not clarification_question:
        return
    categories = _anchor_categories(user_message, goal)
    if not categories:
        return
    if _question_is_side_detail(clarification_question):
        raise ValueError("anchored clarification question drifted into side detail")
    if not _question_mentions_anchor_context(clarification_question, categories):
        raise ValueError("anchored clarification question must stay within the known anchor")


# _validate_goal_analysis_fields
def _validate_goal_analysis_fields(
    fields: dict[str, str],
    *,
    user_message: str,
    state: CurrentState,
) -> dict[str, Any]:
    goal = _parse_nullable_text(fields.get("goal", ""))

    goal_status = str(fields.get("goal_status") or "").strip()
    if goal_status not in _GOAL_STATUS_VALUES:
        raise ValueError(f"goal_status must be one of: {', '.join(sorted(_GOAL_STATUS_VALUES))}")

    needs_clarification = _parse_boolean_field(fields.get("needs_clarification", ""), "needs_clarification")
    clarification_question = _parse_nullable_text(fields.get("clarification_question", ""))

    clarification_reason = str(fields.get("clarification_reason") or "").strip()
    if not clarification_reason:
        raise ValueError("clarification_reason must be a non-empty string")

    enough_context_for_support = _parse_boolean_field(
        fields.get("enough_context_for_support", ""),
        "enough_context_for_support",
    )
    enough_context_for_plan = _parse_boolean_field(
        fields.get("enough_context_for_plan", ""),
        "enough_context_for_plan",
    )

    state_hints: dict[str, Any] = {
        "signals": _parse_csv_list(fields.get("state_hints.signals", "")),
        "risk_flags": _parse_csv_list(fields.get("state_hints.risk_flags", "")),
        "facts": _parse_csv_list(fields.get("state_hints.facts", "")),
    }
    for key in ("domain", "intent"):
        value = _parse_nullable_text(fields.get(f"state_hints.{key}", ""))
        if value:
            state_hints[key] = value

    if needs_clarification and not clarification_question:
        raise ValueError("clarification_question is required when needs_clarification=true")

    _validate_anchor_consistency(
        user_message=user_message,
        state=state,
        goal=goal,
        goal_status=goal_status,
    )
    _validate_clarification_question_quality(
        user_message=user_message,
        state=state,
        goal=goal,
        needs_clarification=needs_clarification,
        clarification_question=clarification_question,
    )

    return {
        "used": True,
        "goal": goal,
        "goal_status": goal_status,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "clarification_reason": clarification_reason,
        "enough_context_for_support": enough_context_for_support,
        "enough_context_for_plan": enough_context_for_plan,
        "state_hints": state_hints,
        "reason": goal_status,
    }


# _build_goal_analysis_system_prompt
def _build_goal_analysis_system_prompt(previous_error: str | None = None) -> str:
    retry_instruction = ""
    if previous_error:
        retry_instruction = (
            "\nPrevious attempt was invalid. "
            f"Problem: {previous_error}. "
            "Retry and return only the fixed field block, one field per line, with no prose before or after."
        )

    return (
        "You analyze one turn of a Russian patient-support chatbot. "
        "Return only a fixed field block, one field per line, with no JSON, no markdown, and no prose before or after.\n"
        "Required fields:\n"
        "goal: <text or null>\n"
        "goal_status: <resolved|generic_distress|context_missing|unclear|correction>\n"
        "needs_clarification: <true|false>\n"
        "clarification_question: <text or null>\n"
        "clarification_reason: <machine-readable label>\n"
        "enough_context_for_support: <true|false>\n"
        "enough_context_for_plan: <true|false>\n"
        "state_hints.signals: <comma-separated values or none>\n"
        "state_hints.risk_flags: <comma-separated values or none>\n"
        "state_hints.facts: <comma-separated values or none>\n"
        "state_hints.domain: <text or null>\n"
        "state_hints.intent: <text or null>\n"
        "Rules:\n"
        "- If the user expresses only generic anxiety, fear, tension, or 'I feel bad' without a clear cause, use goal_status=generic_distress, goal=null, needs_clarification=true.\n"
        "- For generic distress, clarification_question must be one short open question in Russian, without options or menu-like wording.\n"
        "- If the context is already anchored, such as dialysis, medication, symptoms, or a specific upcoming event, use needs_clarification=false and provide a concrete goal.\n"
        "- If an anchor is already known but one short clarification is still needed, keep the question inside that anchor, for example ask what exactly about the dialysis or pressure is worrying the user most.\n"
        "- Do not drift into operational side-detail questions like frequency, schedule, duration, or logistics when the anchor is already known.\n"
        "- If the user is correcting the previous understanding, use goal_status=correction.\n"
        "- Use null for missing scalar fields. Use none for empty list fields.\n"
        "- clarification_reason must always be a short machine-readable label such as generic_distress, context_missing, resolved, or correction."
        + retry_instruction
    )


# _build_goal_analysis_user_prompt
def _build_goal_analysis_user_prompt(user_message: str, state: CurrentState) -> str:
    pending_question = state.pending_question.question_text if state.pending_question else "none"
    pending_slot = state.pending_question.slot_name if state.pending_question else "none"
    pending_reason = state.pending_question.reason if state.pending_question else "none"
    return (
        "Latest user message:\n"
        f"{user_message}\n\n"
        "Current state before this turn:\n"
        f"- domain: {state.domain}\n"
        f"- intent: {state.intent}\n"
        f"- goal: {state.goal}\n"
        f"- pending_slot: {pending_slot}\n"
        f"- pending_question: {pending_question}\n"
        f"- pending_reason: {pending_reason}\n"
        f"- needs_clarification: {state.needs_clarification}\n"
        f"- clarification_streak: {state.clarification_streak}\n"
        f"- last_clarification_reason: {state.last_clarification_reason}\n"
        f"- last_goal_status: {state.last_goal_status}\n"
        f"- signals: {', '.join(str(item) for item in state.signals) or 'none'}\n"
        f"- risk_flags: {', '.join(str(item) for item in state.risk_flags) or 'none'}\n"
        f"- facts: {', '.join(str(item) for item in state.facts) or 'none'}\n"
        "Decide whether the context is sufficient for support or planning right now."
    )


# _excerpt
def _excerpt(text: str, limit: int = 180) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


# _extract_goal_analysis
async def _extract_goal_analysis(
    user_message: str,
    state: CurrentState,
    model_tier: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    client = await pool.get_available(model_tier)
    failures: list[dict[str, Any]] = []
    total_tokens_in = 0
    total_tokens_out = 0
    total_latency_ms = 0
    previous_error: str | None = None

    for attempt in range(1, _MAX_ANALYSIS_ATTEMPTS + 1):
        text, tokens_in, tokens_out, latency_ms = await client.call(
            [{"role": "user", "content": _build_goal_analysis_user_prompt(user_message, state)}],
            _build_goal_analysis_system_prompt(previous_error),
        )
        total_tokens_in += int(tokens_in or 0)
        total_tokens_out += int(tokens_out or 0)
        total_latency_ms += int(latency_ms or 0)

        try:
            payload = _parse_field_block(text)
            analysis = _validate_goal_analysis_fields(
                payload,
                user_message=user_message,
                state=state,
            )
            diagnostics = {
                "attempts_total": attempt,
                "succeeded_on_attempt": attempt,
                "failures": failures,
                "final_status": "success",
                "account_id": client.account_id,
                "actual_model_tier": client.model_tier,
                "tokens_input": total_tokens_in,
                "tokens_output": total_tokens_out,
                "latency_ms": total_latency_ms,
            }
            return analysis, diagnostics
        except (TypeError, ValueError) as exc:
            previous_error = str(exc)
            failures.append(
                {
                    "attempt": attempt,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                    "raw_excerpt": _excerpt(text),
                }
            )
            logger.warning(
                "[supervisor] invalid goal analysis attempt=%d/%d error=%s",
                attempt,
                _MAX_ANALYSIS_ATTEMPTS,
                exc,
            )

    diagnostics = {
        "attempts_total": _MAX_ANALYSIS_ATTEMPTS,
        "succeeded_on_attempt": None,
        "failures": failures,
        "final_status": "failed_after_retries",
        "account_id": client.account_id,
        "actual_model_tier": client.model_tier,
        "tokens_input": total_tokens_in,
        "tokens_output": total_tokens_out,
        "latency_ms": total_latency_ms,
    }
    return None, diagnostics


# _prefetch_supervisor_context
async def _prefetch_supervisor_context(context: PipelineContext) -> None:
    if not context.request.db or not _needs_support_grounding(context):
        return

    try:
        from app.llm.context_builder_optimized import build_context_bundle_optimized

        context_bundle = await build_context_bundle_optimized(
            context.request.patient_id,
            context.request.db,
            query=context.request.user_input,
        )
        context.patient_context = context_bundle["context"]
        context.memory_reads = _build_memory_reads(context.patient_context)
        context.diagnostics["patient_context"] = {
            **context_bundle["diagnostics"],
            "skipped": True,
            "reason": "supervisor_prefetch",
        }
        context.diagnostics["memory"] = {
            "reads": context.memory_reads,
            "skipped": True,
            "reason": "supervisor_prefetch",
        }
    except Exception as exc:  # pragma: no cover - retrieval should not kill the request
        logger.warning(
            "[supervisor] context prefetch failed patient=%d: %s",
            context.request.patient_id,
            exc,
        )


# _render_grounding_for_prompt
def _render_grounding_for_prompt(context: PipelineContext) -> str:
    patient_context = dict(context.patient_context or {})
    rag_views = dict(patient_context.get("rag_views") or {})
    psych_support_items = [str(item).strip() for item in (rag_views.get("psych_support") or []) if str(item).strip()]
    education_items = [str(item).strip() for item in (rag_views.get("education") or []) if str(item).strip()]

    if not psych_support_items and not education_items:
        return "Grounded support material: none."

    lines: list[str] = []
    if psych_support_items:
        lines.append("Grounded psych_support practice metadata:")
        lines.extend(f"- {item}" for item in psych_support_items[:2])
    if education_items and not psych_support_items:
        lines.append("Grounded education fragments:")
        lines.extend(f"- {item}" for item in education_items[:2])
    return "\n".join(lines)


# _build_supervisor_system_prompt
def _build_supervisor_system_prompt() -> str:
    return (
        "Write the final patient-facing reply in Russian. "
        "Sound natural, warm, and human, not scripted. "
        "Do not mention internal state, agents, routing, diagnostics, or policies. "
        "Do not open every reply with the same phrase.\n"
        "Follow response_mode exactly.\n"
        "- If response_mode=hybrid_clarify, produce exactly three semantic parts: "
        "one short validating sentence, one very safe in-the-moment micro-step, and one open clarification question in Russian.\n"
        "- If response_mode=clarify_only, ask only one short open clarification question in Russian, with no extra advice.\n"
        "- If response_mode=direct_support or direct_plan, provide help without forcing an extra follow-up question unless it is truly needed.\n"
        "- If grounded psych_support metadata is relevant, you may use it for one concrete coping step.\n"
        "- Keep the reply concise and patient-friendly."
    )


# _build_supervisor_user_prompt
def _build_supervisor_user_prompt(context: PipelineContext) -> str:
    turn = context.supervisor_turn
    state = dict(context.supervisor_state or {})
    supervisor_diagnostics = context.diagnostics.get("supervisor") or {}
    goal_analysis = supervisor_diagnostics.get("goal_analysis") or {}
    response_mode = supervisor_diagnostics.get("response_mode")
    context_sufficiency = supervisor_diagnostics.get("context_sufficiency") or {}
    return (
        "Latest user message:\n"
        f"{context.request.user_input}\n\n"
        "Supervisor draft:\n"
        f"{turn.reply}\n\n"
        "Normalized goal analysis:\n"
        f"- goal: {goal_analysis.get('goal')}\n"
        f"- goal_status: {goal_analysis.get('goal_status')}\n"
        f"- needs_clarification: {goal_analysis.get('needs_clarification')}\n"
        f"- clarification_reason: {goal_analysis.get('clarification_reason')}\n"
        f"- enough_context_for_support: {context_sufficiency.get('support')}\n"
        f"- enough_context_for_plan: {context_sufficiency.get('plan')}\n"
        f"- response_mode: {response_mode}\n\n"
        "Current state after this turn:\n"
        f"- message_type: {turn.message_type}\n"
        f"- needs_clarification: {turn.needs_clarification}\n"
        f"- selected_agents: {', '.join(turn.selected_agents) if turn.selected_agents else 'none'}\n"
        f"- domain: {state.get('domain')}\n"
        f"- intent: {state.get('intent')}\n"
        f"- goal: {state.get('goal')}\n"
        f"- signals: {', '.join(str(item) for item in (state.get('signals') or [])) or 'none'}\n"
        f"- risk_flags: {', '.join(str(item) for item in (state.get('risk_flags') or [])) or 'none'}\n\n"
        f"{_render_grounding_for_prompt(context)}\n\n"
        "Rewrite the supervisor draft into the final patient-facing answer in Russian. "
        "Respect response_mode literally."
    )


class SupervisorStage(PipelineStage):
    """Stage 1.5: main stateful supervisor turn."""

    @property
    def stage_name(self) -> str:
        return "supervisor"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()

        if context.classification.request_type in {RequestType.SAFETY, RequestType.QUICK_ACTION}:
            context.diagnostics["supervisor"] = {
                "enabled": False,
                "reason": "legacy_path",
                "latency_ms": 0,
            }
            return context

        current_state = CurrentState.from_dict(context.supervisor_state)
        goal_analysis, goal_analysis_diagnostics = await _extract_goal_analysis(
            user_message=context.request.user_input,
            state=current_state,
            model_tier=context.classification.model_tier.value,
        )
        if goal_analysis is None:
            context.diagnostics["supervisor"] = {
                "enabled": True,
                "goal_analysis": {
                    "used": True,
                    "goal": None,
                    "goal_status": None,
                    "needs_clarification": None,
                    "clarification_reason": None,
                    "clarification_question": None,
                    "state_hints": {},
                    **goal_analysis_diagnostics,
                },
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            raise LLMResponseError(
                "supervisor goal analysis failed after 3 attempts",
                diagnostics={
                    "supervisor": dict(context.diagnostics["supervisor"]),
                },
            )

        supervisor_diagnostics: dict[str, Any] = {
            "enabled": True,
            "goal_analysis": {
                **goal_analysis,
                **goal_analysis_diagnostics,
            },
            "goal_extraction": {
                "used": True,
                "goal": goal_analysis.get("goal"),
                "reason": goal_analysis.get("goal_status"),
                "needs_clarification": goal_analysis.get("needs_clarification"),
            },
        }

        orchestrator = SupervisorOrchestrator()
        turn = orchestrator.handle_message(
            user_message=context.request.user_input,
            current_state=current_state,
            goal_resolution=goal_analysis,
        )
        supervisor_diagnostics["response_mode"] = turn.diagnostics.get("response_mode")
        supervisor_diagnostics["context_sufficiency"] = dict(turn.diagnostics.get("context_sufficiency") or {})

        context.supervisor_turn = turn
        context.supervisor_state = turn.updated_state.to_dict()
        context.should_skip_orchestration = True

        await _prefetch_supervisor_context(context)

        client = await pool.get_available(context.classification.model_tier.value)
        drafted_text, tokens_in, tokens_out, latency_ms = await client.call(
            [{"role": "user", "content": _build_supervisor_user_prompt(context)}],
            _build_supervisor_system_prompt(),
        )
        drafted_text = str(drafted_text or "").strip()
        if not drafted_text:
            raise LLMResponseError(
                "supervisor draft rewrite returned empty text",
                diagnostics={
                    "supervisor": {
                        **supervisor_diagnostics,
                        "message_type": turn.message_type,
                        "selected_agents": list(turn.selected_agents),
                        "used_pending_answer": turn.used_pending_answer,
                        "needs_clarification": turn.needs_clarification,
                        "state_delta": dict(turn.state_delta),
                        "state_after": dict(context.supervisor_state),
                        "turn_diagnostics": dict(turn.diagnostics),
                    }
                },
            )

        context.response_draft = drafted_text
        context.response_tokens_input = int(tokens_in or 0)
        context.response_tokens_output = int(tokens_out or 0)
        context.response_account_id = "SUPERVISOR"
        context.response_actual_model_tier = client.model_tier
        context.diagnostics["llm_call"] = {
            "model": client.model_tier,
            "account_id": client.account_id,
            "tokens_input": int(tokens_in or 0),
            "tokens_output": int(tokens_out or 0),
            "latency_ms": int(latency_ms or 0),
            "source": "supervisor_draft",
        }

        supervisor_diagnostics.update(
            {
                "message_type": turn.message_type,
                "selected_agents": list(turn.selected_agents),
                "used_pending_answer": turn.used_pending_answer,
                "needs_clarification": turn.needs_clarification,
                "state_delta": dict(turn.state_delta),
                "state_after": dict(context.supervisor_state),
                "turn_diagnostics": dict(turn.diagnostics),
                "clarification_analysis": {
                    "needs_clarification": goal_analysis.get("needs_clarification"),
                    "clarification_reason": goal_analysis.get("clarification_reason"),
                    "clarification_question": goal_analysis.get("clarification_question"),
                    "enough_context_for_support": goal_analysis.get("enough_context_for_support"),
                    "enough_context_for_plan": goal_analysis.get("enough_context_for_plan"),
                },
                "llm_draft": {
                    "enabled": True,
                    "used": True,
                    "source": "llm",
                    "account_id": client.account_id,
                    "actual_model_tier": client.model_tier,
                    "tokens_input": int(tokens_in or 0),
                    "tokens_output": int(tokens_out or 0),
                    "latency_ms": int(latency_ms or 0),
                    "grounded_psych_support_items": len(
                        (context.patient_context.get("rag_views") or {}).get("psych_support", [])
                    )
                    if context.patient_context
                    else 0,
                },
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        )
        context.diagnostics["supervisor"] = supervisor_diagnostics

        logger.info(
            "[supervisor] patient=%d message_type=%s agents=%s clarify=%s goal_status=%s analysis_attempt=%s",
            context.request.patient_id,
            turn.message_type,
            ",".join(turn.selected_agents) or "-",
            turn.needs_clarification,
            goal_analysis.get("goal_status"),
            goal_analysis_diagnostics.get("succeeded_on_attempt"),
        )

        return context
