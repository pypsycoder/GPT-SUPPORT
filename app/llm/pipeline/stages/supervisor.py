"""Supervisor Stage powered by Graph v2: intake -> delegation -> emotional expert."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.llm import agent, memory_store, prompt_assembly, router_l0, safety_responses, tools
from app.llm.context_builder_optimized import build_context_bundle_optimized
from app.llm.errors import LLMResponseError
from app.llm.langgraph_supervisor import ExecutionKind, FirstModuleInput, run_first_module
from app.llm.pool import session_key
from app.llm.langgraph_supervisor.models import EducationExpertCard, EmotionalExpertCard, ExpertStrategy
from app.llm.technique_library import get_technique_by_id
from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.supervisor import CurrentState, PendingQuestion, SupervisorTurnResult
from app.llm.supervisor.classification import detect_message_type

logger = logging.getLogger("gpt-support-llm.pipeline.supervisor")


def _derive_message_type(user_message: str, current_state: CurrentState) -> str:
    return detect_message_type(user_message, current_state)


_EXPERT_CLOSE_STRATEGY = "завершить"


def _resolve_model_tier(
    requested_tier: str,
    current_state: CurrentState,
    *,
    strict: bool,
    education_grounding_available: bool = False,
) -> str:
    """Upgrade lite→pro when an active expert session is detected or education grounding is loaded.

    classify_request() knows nothing about supervisor state, so short follow-up
    messages in an ongoing emotional/education session get tier=lite.  The expert
    nodes (11 fields for emotional, 7 fields for education) reliably fail on
    GigaChat-2; a pro-tier upgrade prevents the 3-retry failure cascade.

    education_grounding_available=True means RAG found education content — the
    request will almost certainly go to the education expert, so upgrade on the
    first turn too (before education_session_active is set).

    strict=True (researcher debug with forced tier) is never upgraded.
    """
    if strict or requested_tier != "lite":
        return requested_tier
    emotional_active = (
        "emotional_support" in current_state.last_selected_agents
        and current_state.last_expert_strategy != _EXPERT_CLOSE_STRATEGY
    )
    education_active = (
        current_state.education_session_active
        and "education" in current_state.last_selected_agents
    )
    if emotional_active or education_active or education_grounding_available:
        return "pro"
    return requested_tier


def _changed_state(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed[key] = after.get(key)
    return changed


_CONTEXT_PLACEHOLDER = "контекст пока не раскрыт"

_UNKNOWN_REASON_PHRASES = (
    "причина тревоги неизвестна",
    "причина пользователю не известна",
    "причина не известна",
    "причина неизвестна",
)


def _has_unknown_reason(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _UNKNOWN_REASON_PHRASES)


def _strip_unknown_reason_sentences(text: str) -> str:
    parts = [p.strip() for p in text.split(".") if p.strip()]
    parts = [p for p in parts if not _has_unknown_reason(p)]
    return ". ".join(parts)


def _normalize_for_compare(text: str) -> str:
    """Collapse consecutive dots and whitespace for substring comparison."""
    result = text
    while ".." in result:
        result = result.replace("..", ".")
    return " ".join(result.split()).strip()


def _strip_placeholder(text: str) -> str:
    """Remove leading placeholder sentences from accumulated context."""
    parts = [p.strip() for p in text.split(".") if p.strip()]
    parts = [p for p in parts if p.lower() != _CONTEXT_PLACEHOLDER]
    return ". ".join(parts)


def _merge_intake_context(previous: str | None, current: str | None, *, preserve_history: bool) -> str | None:
    previous_text = str(previous or "").strip()
    current_text = str(current or "").strip()
    if not current_text or current_text.lower() == _CONTEXT_PLACEHOLDER:
        return previous_text or None
    # Replace placeholder-only previous with real context
    if previous_text.lower() == _CONTEXT_PLACEHOLDER:
        previous_text = ""
    if not preserve_history or not previous_text or previous_text == current_text:
        return current_text
    # Strip any stale placeholder from accumulated text before merging
    previous_clean = _strip_placeholder(previous_text)
    # Strip "unknown reason" stubs if new context provides a concrete cause
    if not _has_unknown_reason(current_text):
        previous_clean = _strip_unknown_reason_sentences(previous_clean)
    if not previous_clean or previous_clean == current_text:
        return current_text
    # Normalize before substring checks to handle "..." vs "." inconsistencies
    previous_norm = _normalize_for_compare(previous_clean)
    current_norm = _normalize_for_compare(current_text)
    if current_norm in previous_norm:
        return previous_clean
    if previous_norm in current_norm:
        return current_text
    return f"{previous_clean}. {current_text}"


def _build_updated_state(current_state: CurrentState, graph_state) -> CurrentState:
    updated = CurrentState.from_dict(current_state.to_dict())
    intake_card = graph_state.intake_card

    if intake_card is not None:
        if intake_card.problem and intake_card.problem != "не обозначена":
            updated.goal = intake_card.problem

        merged_context = _merge_intake_context(
            current_state.slots.get("intake_context"),
            intake_card.context,
            preserve_history=bool(current_state.pending_question or current_state.clarification_streak),
        )
        if merged_context:
            updated.slots["intake_context"] = merged_context

    if graph_state.execution_kind is ExecutionKind.ASK:
        previous_attempts = updated.pending_question.attempts if updated.pending_question else 0
        updated.pending_question = PendingQuestion(
            slot_name="clarify",
            question_text=graph_state.user_question or "",
            expected_kind="free_text",
            attempts=previous_attempts + 1,
            reason="intake",
        )
        updated.needs_clarification = True
        updated.clarification_streak = int(updated.clarification_streak or 0) + 1
        updated.last_selected_agents = []
        # ASK comes only through normal intake (not education bypass) → topic has changed
        if current_state.education_session_active:
            updated.education_session_active = False
            updated.education_topic = None
            updated.education_turn_count = 0
    elif graph_state.execution_kind is ExecutionKind.DELEGATE:
        expert_card = getattr(graph_state, "expert_card", None)
        follow_up = str(getattr(expert_card, "follow_up", "") or "").strip()
        if bool(graph_state.needs_clarification) and follow_up and follow_up.lower() != "нет":
            previous_attempts = (
                updated.pending_question.attempts
                if updated.pending_question and updated.pending_question.reason == "expert"
                else 0
            )
            updated.pending_question = PendingQuestion(
                slot_name="expert_follow_up",
                question_text=follow_up,
                expected_kind="free_text",
                attempts=previous_attempts + 1,
                reason="expert",
            )
            updated.needs_clarification = True
        else:
            updated.pending_question = None
            updated.needs_clarification = False
        updated.clarification_streak = 0
        updated.last_selected_agents = list(graph_state.selected_agents)
    else:
        updated.pending_question = None
        updated.needs_clarification = False
        updated.clarification_streak = 0
        updated.last_selected_agents = []
        if current_state.education_session_active:
            updated.education_session_active = False
            updated.education_topic = None
            updated.education_turn_count = 0

    final_reply = getattr(graph_state, "final_reply", None)
    if final_reply:
        updated.last_bot_reply = str(final_reply).strip() or None

    expert_card = getattr(graph_state, "expert_card", None)

    # anchor_goal: set once on first delegation, never overwritten
    if updated.anchor_goal is None and intake_card is not None:
        problem = str(getattr(intake_card, "problem", "") or "").strip()
        if problem and problem != "не обозначена":
            updated.anchor_goal = problem

    if isinstance(expert_card, EducationExpertCard):
        updated.education_session_active = True
        if intake_card is not None:
            problem = str(getattr(intake_card, "problem", "") or "").strip()
            if problem and problem != "не обозначена":
                updated.education_topic = problem
        updated.education_turn_count = int(updated.education_turn_count or 0) + 1

    elif isinstance(expert_card, EmotionalExpertCard):
        updated.education_session_active = False
        updated.education_topic = None
        updated.education_turn_count = 0

    if isinstance(expert_card, EmotionalExpertCard):
        # session_plan: written by expert each turn
        if expert_card.session_plan:
            updated.session_plan = expert_card.session_plan

        # branch state machine
        action = expert_card.branch_action
        if action == "open":
            updated.on_branch = True
            updated.branch_type = expert_card.branch_type or None
            updated.branch_turns = 1
            updated.branch_return_intent = (
                expert_card.branch_return_intent
                if expert_card.branch_return_intent not in ("нет", "none", "")
                else None
            )
        elif action == "continue":
            updated.branch_turns = int(updated.branch_turns or 0) + 1
        elif action == "close":
            updated.on_branch = False
            updated.branch_type = None
            updated.branch_turns = 0
            updated.branch_return_intent = None
        # action == "none" → branch state unchanged

        updated.last_expert_effectiveness = expert_card.effectiveness.value
        updated.last_expert_strategy = expert_card.strategy.value
        step = str(expert_card.step_now or "").strip()
        match = re.match(r'^\[(p\d+)\]', step)
        new_technique_id = match.group(1) if match else None
        step_text = step[match.end():].strip() if match else None
        # If the model wrote just "[pNN]" with no text, don't credit it as a delivered step.
        if new_technique_id and not step_text:
            new_technique_id = None
        # Defensive: if we're mid-interactive-flow and expert omitted [pNN] prefix,
        # auto-attribute the step to the current technique so step index advances.
        _step_is_action = step and step.lower() not in ("нет", "no", "")
        if new_technique_id is None and _step_is_action:
            _current_id = str(current_state.current_technique_id or "").strip()
            if _current_id:
                _card = get_technique_by_id(_current_id)
                if _card and _card.interactive:
                    new_technique_id = _current_id
                    step_text = step
        # Preserve current_technique_id during reflection/follow-up turns (step_now = нет).
        # Only clear it when explicitly closing or when a new technique is delivered.
        if new_technique_id is not None:
            updated.current_technique_id = new_technique_id
        elif expert_card.strategy is ExpertStrategy.CLOSE:
            updated.current_technique_id = None
        # else: продолжить/углубить with follow_up — keep current_technique_id from state copy
        updated.last_expert_step = step_text or None
        if new_technique_id:
            recent = list(updated.recent_technique_ids)
            if not recent or recent[-1] != new_technique_id:
                recent.append(new_technique_id)
            updated.recent_technique_ids = recent[-5:]
            if new_technique_id == current_state.current_technique_id:
                updated.current_technique_turns = int(current_state.current_technique_turns or 0) + 1
            else:
                updated.current_technique_turns = 1
            # Advance step index for interactive techniques
            card = get_technique_by_id(new_technique_id)
            if card and card.interactive:
                if new_technique_id != current_state.current_technique_id:
                    updated.current_step_index = 1  # just delivered step 0
                else:
                    prev = int(current_state.current_step_index or 0)
                    if prev >= len(card.steps):
                        # All steps delivered — mark exhausted so next turn goes to selection list
                        updated.current_step_index = len(card.steps) + 1
                    else:
                        updated.current_step_index = min(prev + 1, len(card.steps))
            else:
                updated.current_step_index = 0

    return updated


async def _load_education_grounding(
    context: PipelineContext,
    *,
    query_override: str | None = None,
    skip_rag: bool = False,
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Возвращает (education view, grounding items, диагностика, сырой контекст пациента).

    Сырой контекст нужен послойной сборке промпта: из него строятся стабильные
    слои [1] профиль и [3] окно диалога.

    ``skip_rag=True`` (шаг 7, одноагентная ветка с инструментами): RAG-поиск
    не запускается вовсе — агент получит ``search_education`` как инструмент
    и сходит за материалами сам, только если реально понадобится. Остальные
    секции (витальные, история чата, устойчивые факты) собираются как обычно —
    ``build_context_bundle_optimized`` гейтит RAG-блок по длине запроса
    (``len(query) >= 10``), поэтому пустой query достаточен, чтобы его
    пропустить, не трогая остальную сборку. НЕ через ``query_override=""``:
    пустая строка falsy и утекла бы в ``query_override or user_input``.
    """
    if context.request.db is None:
        return [], [], {"enabled": False, "reason": "db_unavailable"}, {}

    query = "" if skip_rag else (query_override or context.request.user_input)
    try:
        bundle = await build_context_bundle_optimized(
            context.request.patient_id,
            context.request.db,
            query,
            thread_id=context.request.thread_id,
        )
    except Exception as exc:
        logger.warning("[supervisor] education grounding failed patient=%d: %s", context.request.patient_id, exc)
        return [], [], {"enabled": False, "reason": "grounding_error", "error": str(exc)}, {}

    context_payload = dict(bundle.get("context") or {})
    rag_views = dict(context_payload.get("rag_views") or {})
    grounding_items = [
        dict(item) for item in (context_payload.get("rag_grounding_items") or []) if isinstance(item, dict)
    ]
    education_view = [str(item) for item in (rag_views.get("education") or []) if str(item).strip()]
    context_payload["stable_facts"] = await memory_store.list_active_facts_text(
        context.request.db, context.request.patient_id
    )
    diagnostics = {
        "enabled": True,
        "skip_rag": skip_rag,
        "view_count": len(education_view),
        "grounding_count": len(grounding_items),
        "rag": dict((bundle.get("diagnostics") or {}).get("rag") or {}),
    }
    return education_view, grounding_items, diagnostics, context_payload


_ALERT_NOTES = {
    "bp_critical": (
        "Давление в кризисной зоне. Отметь это прямо, предложи перемерить через "
        "несколько минут в покое и связаться с диализным центром. Не диагностируй "
        "и не назначай ничего."
    ),
    "bp_high": "Давление выше обычного — стоит отметить спокойно, без нагнетания.",
}


def _l0_note(decision) -> str:
    """Что L0 разобрал детерминированно — передаём агенту как факты, а не догадки."""
    if decision is None:
        return ""
    lines: list[str] = []

    if decision.vitals:
        rendered = []
        for item in decision.vitals:
            if item.get("type") == "BP":
                rendered.append(f"АД {item['systolic']}/{item['diastolic']}")
            else:
                rendered.append(f"{item['type']} {item['value']}")
        lines.append("Пациент назвал показатели: " + ", ".join(rendered) + ".")

    if decision.alert and decision.alert in _ALERT_NOTES:
        lines.append(_ALERT_NOTES[decision.alert])

    if decision.safety_level == "concern":
        lines.append(
            "В сообщении есть признак истощения или безнадёжности "
            f"({decision.rule}). Отнесись внимательнее, но не приписывай человеку "
            "того, чего он не говорил."
        )

    if decision.intent == "continuation" and decision.continued_intent:
        lines.append(
            f"Это короткий ответ на твой предыдущий вопрос — продолжение темы "
            f"«{decision.continued_intent}», а не новый запрос."
        )

    return "\n".join(lines)


_SAFETY_ORDER = {"none": 0, "concern": 1, "urgent": 2}


def _apply_agent_safety_net(context: PipelineContext, reply_card) -> dict[str, Any]:
    """Второй эшелон защиты поверх вердикта агента.

    Делает две вещи, и обе про ложноотрицательные срабатывания L0:

    1. **Считает пропуски на живом трафике.** Ход, где агент увидел риск, а L0
       промолчал, — это и есть пропуск L0. Других способов мерить полноту
       непрерывно у нас нет: разовые замеры идут по выборкам, каждая из которых
       чем-нибудь смещена.
    2. **Перекрывает ответ при urgent.** Вердикт приходит уже после генерации,
       поэтому предотвратить вызов он не может — но выбросить текст и подставить
       протокол ничего не стоит, а цена ошибки здесь максимальная.

    Оговорка: детекторы не независимы. Это та же модель, и при ``concern`` от L0
    она получает подсказку через ``_l0_note``. Чище всего сигнал там, где L0
    промолчал — то есть ровно в интересующем нас случае.
    """
    l0_level = str(getattr(context.l0, "safety_level", "none") or "none")
    agent_level = str(reply_card.safety_level or "none")
    agent_kind = str(getattr(reply_card, "safety_kind", "none") or "none")

    missed_by_l0 = _SAFETY_ORDER.get(agent_level, 0) > _SAFETY_ORDER.get(l0_level, 0)
    escalated = agent_level == "urgent"

    reply = safety_responses.crisis_response(agent_kind) if escalated else reply_card.reply.strip()

    if escalated:
        logger.warning(
            "[safety_net] агент поднял urgent (kind=%s, l0=%s) patient=%d — ответ перекрыт. Причина: %s",
            agent_kind,
            l0_level,
            context.request.patient_id,
            str(reply_card.safety_reason)[:120],
        )
    elif missed_by_l0:
        # Не кризис, но L0 не заметил того, что заметил агент. Копим для замера.
        logger.info(
            "[safety_net] L0 промолчал, агент дал %s patient=%d: %s",
            agent_level,
            context.request.patient_id,
            str(reply_card.safety_reason)[:120],
        )

    return {
        "reply": reply,
        "l0_level": l0_level,
        "agent_level": agent_level,
        "agent_kind": agent_kind,
        "missed_by_l0": missed_by_l0,
        "reply_overridden": escalated,
    }


def _single_agent_applicable(context: PipelineContext) -> bool:
    """Идёт ли этот ход по одноагентной ветке.

    Раньше здесь было общее исключение для ``request_type=SAFETY`` — «кризисный
    путь остаётся на старой ветке, пока не наберётся статистика» (00_MANUAL.md,
    часть 13). Но настоящий подтверждённый кризис (``L0.safety_level=='urgent'``)
    сюда никогда не доходит: ``BoundaryGuardStage`` перехватывает его через
    ``context.early_response`` и обрывает пайплайн до ``ClassificationStage``/
    ``SupervisorStage`` (см. boundary_guard.py). Значит на этот код ни разу не
    попадал настоящий L0-подтверждённый кризис — только «серая зона»: то, что
    L1/L2 сами для себя пометили как safety при отсутствии однозначных
    L0-паттернов (см. router_l2.py: «при сомнении — выбирай safety»). Именно
    там старая ветка (intake→delegation→expert) показала живой баг на
    многосоставном тревожном вводе (patient-sim, s05_anxious, 2026-08-25) —
    не пройдя валидацию intake-карточки, тогда как одноагентная ветка такой
    ввод обрабатывает штатно. Собственная эскалация внутри одноагентной ветки
    (``AgentReply.safety_level`` → ``crisis_response()`` в ``_run_single_agent``)
    не завязана на request_type и продолжает работать независимо.
    """
    if not agent.single_agent_enabled():
        return False
    if context.classification is None:
        return False
    return True


def _agent_intent_to_agents(intent: str) -> list[str]:
    """Намерение агента → список агентов в терминах старой ветки, для сравнимости."""
    mapping = {
        "emotional_support": ["emotional_support"],
        "education": ["education"],
        "safety": ["safety"],
        "smalltalk": [],
    }
    return list(mapping.get(intent, []))


_AGENT_ERROR_REPLY = (
    "Прошу прощения, у меня техническая заминка с ответом. "
    "Повтори, пожалуйста, сообщение ещё раз."
)


async def _run_single_agent(
    context: PipelineContext,
    *,
    current_state: CurrentState,
    message_type: str,
    model_tier: str,
    strict_model_tier: bool,
    patient_context: dict[str, Any],
    education_rag_context: list[str],
    education_grounding_diagnostics: dict[str, Any],
    started: float,
    use_agent_tools: bool = False,
) -> PipelineContext:
    """Один структурный вызов вместо intake → delegation → expert.

    Если агент не смог отдать карточку (обе попытки в ``Agent.run`` упали на
    валидации), ход всё равно остаётся на одноагентной ветке — без отката на
    старую 3-вызовную цепочку intake → delegation → expert. Такой откат
    раньше маскировал сбои схемы статистикой старой ветки и утраивал задержку
    хода (два неудачных попытки агента + полный проход старой цепочки, см.
    LLM_test/reports/2026.08.24_21.59.md). Вместо этого пациент получает
    короткий технический ответ, а состояние супервизора не трогается.
    """
    request = context.request
    profile_block = prompt_assembly.build_profile_layer(patient_context)
    history_turns = [
        {"role": item["role"], "content": item["content"]}
        for item in (patient_context.get("chat_history") or [])
        if isinstance(item, dict) and item.get("role") and item.get("content")
    ]
    digest = ""
    if request.db is not None:
        digest = await memory_store.get_digest(
            request.db, patient_id=request.patient_id, thread_id=request.thread_id
        )

    technique_state = agent.TechniqueState(
        current_id=current_state.current_technique_id,
        step_index=int(current_state.current_step_index or 0),
        turns=int(current_state.current_technique_turns or 0),
        recent_ids=list(current_state.recent_technique_ids or []),
    )
    layers = agent.build_layers(
        user_message=request.user_input,
        profile_block=profile_block,
        history=history_turns,
        rag_fragments=education_rag_context,
        patient_gender=request.patient_gender,
        last_bot_reply=current_state.last_bot_reply,
        session_goal=current_state.goal,
        anchor_goal=current_state.anchor_goal,
        digest=digest,
        technique_state=technique_state,
        technique_context=str(current_state.slots.get("intake_context") or ""),
        l0_note=_l0_note(context.l0),
        tools_available=use_agent_tools,
    )
    run = await agent.Agent(
        model_tier=model_tier, strict_model_tier=strict_model_tier
    ).run(
        layers,
        patient_id=request.patient_id,
        thread_key=session_key(request.patient_id, request.thread_id),
        allowed_tools=["search_education"] if use_agent_tools else None,
        db=request.db if use_agent_tools else None,
    )

    if not run.ok or run.reply is None:
        logger.warning(
            "[single_agent] patient=%d не отдал карточку (%s) — технический ответ, без отката на старую ветку",
            request.patient_id,
            run.error,
        )
        updated_state = CurrentState.from_dict(current_state.to_dict())
        updated_state.last_bot_reply = _AGENT_ERROR_REPLY
        before_state = current_state.to_dict()
        after_state = updated_state.to_dict()
        diagnostics = {
            "enabled": True,
            "branch": "single_agent",
            "request_type": context.classification.request_type.value,
            "message_type": message_type,
            "graph_path": ["agent"],
            "selected_agents": list(current_state.last_selected_agents or []),
            "needs_clarification": current_state.needs_clarification,
            "execution_kind": "агент_ошибка",
            "education_grounding": education_grounding_diagnostics,
            "prompt_layers": {
                "enabled": prompt_assembly.layers_enabled(),
                "profile_chars": len(profile_block),
                "window_turns": len(history_turns),
                "prefix_fingerprints": [run.prefix_fp] if run.prefix_fp else [],
            },
            "error": run.error,
            "state_delta": _changed_state(before_state, after_state),
            "state_after": after_state,
            "llm_totals": {
                "tokens_input": run.tokens_in,
                "tokens_output": run.tokens_out,
                "latency_ms": run.latency_ms,
                "account_ids": [run.account_id] if run.account_id else [],
                "actual_model_tiers": [model_tier],
            },
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
        context.supervisor_turn = SupervisorTurnResult(
            reply=_AGENT_ERROR_REPLY,
            state_delta=diagnostics["state_delta"],
            updated_state=updated_state,
            message_type=message_type,
            selected_agents=list(current_state.last_selected_agents or []),
            used_pending_answer=False,
            needs_clarification=current_state.needs_clarification,
            diagnostics=diagnostics,
            education_cta=None,
        )
        context.supervisor_state = after_state
        context.response_draft = _AGENT_ERROR_REPLY
        context.response_tokens_input = run.tokens_in
        context.response_tokens_output = run.tokens_out
        context.response_account_id = run.account_id or "AGENT"
        context.response_actual_model_tier = model_tier
        context.diagnostics["supervisor"] = diagnostics
        return context

    reply_card = run.reply

    # Второй эшелон. L0 работает до вызова и ловит явные формулировки; агент
    # видит сообщение целиком и замечает то, что регулярки пропускают. Его
    # вердикт до сих пор только писался в диагностику — здесь он начинает
    # работать.
    safety_net = _apply_agent_safety_net(context, reply_card)
    patient_reply = safety_net["reply"]

    updated_state = CurrentState.from_dict(current_state.to_dict())
    updated_state.last_bot_reply = patient_reply or None
    updated_state.last_selected_agents = _agent_intent_to_agents(reply_card.intent)
    updated_state.needs_clarification = False
    updated_state.pending_question = None
    updated_state.clarification_streak = 0
    if updated_state.anchor_goal is None and reply_card.intent != "smalltalk":
        updated_state.anchor_goal = current_state.goal

    # Прогресс по технике — по явному полю схемы, а не по префиксу [pNN] в тексте.
    advanced = agent.advance_technique(technique_state, reply_card.technique_id)
    updated_state.current_technique_id = advanced.current_id
    updated_state.current_step_index = advanced.step_index
    updated_state.current_technique_turns = advanced.turns
    updated_state.recent_technique_ids = list(advanced.recent_ids)

    before_state = current_state.to_dict()
    after_state = updated_state.to_dict()

    diagnostics = {
        "enabled": True,
        "branch": "single_agent",
        "request_type": context.classification.request_type.value,
        "message_type": message_type,
        "graph_path": ["agent"],
        "selected_agents": _agent_intent_to_agents(reply_card.intent),
        "needs_clarification": False,
        "execution_kind": "агент",
        "education_grounding": education_grounding_diagnostics,
        "prompt_layers": {
            "enabled": prompt_assembly.layers_enabled(),
            "profile_chars": len(profile_block),
            "window_turns": len(history_turns),
            "prefix_fingerprints": [run.prefix_fp] if run.prefix_fp else [],
        },
        "l0": {
            "enabled": router_l0.l0_enabled(),
            "intent": getattr(context.l0, "intent", None),
            "rule": getattr(context.l0, "rule", None),
            "safety_level": getattr(context.l0, "safety_level", "none"),
            "vitals": list(getattr(context.l0, "vitals", []) or []),
            "alert": getattr(context.l0, "alert", None),
        },
        "safety_net": safety_net,
        "agent": {
            "intent": reply_card.intent,
            "technique_id": reply_card.technique_id,
            "technique_step_index": advanced.step_index,
            "safety_level": reply_card.safety_level,
            "safety_kind": reply_card.safety_kind,
            "safety_reason": reply_card.safety_reason,
            "next_action": reply_card.next_action,
            "memory_candidates": list(reply_card.memory_candidates),
            "llm_calls": run.llm_calls,
            "repair_attempts": run.repair_attempts,
            "attempts_total": run.attempts,
            "tools_enabled": use_agent_tools,
            "tool_hops": run.hops,
        },
        "state_delta": _changed_state(before_state, after_state),
        "state_after": after_state,
        "llm_totals": {
            "tokens_input": run.tokens_in,
            "tokens_output": run.tokens_out,
            "latency_ms": run.latency_ms,
            "account_ids": [run.account_id] if run.account_id else [],
            "actual_model_tiers": [model_tier],
        },
        "latency_ms": int((time.monotonic() - started) * 1000),
    }

    context.supervisor_turn = SupervisorTurnResult(
        reply=patient_reply,
        state_delta=diagnostics["state_delta"],
        updated_state=updated_state,
        message_type=message_type,
        selected_agents=_agent_intent_to_agents(reply_card.intent),
        used_pending_answer=False,
        needs_clarification=False,
        diagnostics=diagnostics,
        education_cta=None,
    )
    context.supervisor_state = after_state
    context.response_draft = patient_reply
    context.response_tokens_input = run.tokens_in
    context.response_tokens_output = run.tokens_out
    context.response_account_id = run.account_id or "AGENT"
    context.response_actual_model_tier = model_tier
    context.diagnostics["supervisor"] = diagnostics

    logger.info(
        "[single_agent] patient=%d intent=%s safety=%s calls=%d tokens=%d+%d",
        request.patient_id,
        reply_card.intent,
        reply_card.safety_level,
        run.llm_calls,
        run.tokens_in,
        run.tokens_out,
    )
    return context


def _raise_if_failed(graph_state, supervisor_diagnostics: dict[str, Any]) -> None:
    intake_llm = ((graph_state.diagnostics.get("intake") or {}).get("llm") or {})
    if intake_llm.get("final_status") == "failed_after_retries":
        raise LLMResponseError(
            "supervisor intake analysis failed after 3 attempts",
            diagnostics={"supervisor": supervisor_diagnostics},
        )

    delegation_llm = ((graph_state.diagnostics.get("delegation") or {}).get("llm") or {})
    if graph_state.execution_kind is ExecutionKind.DELEGATE and delegation_llm.get("final_status") == "failed_after_retries":
        raise LLMResponseError(
            "supervisor delegation analysis failed after 3 attempts",
            diagnostics={"supervisor": supervisor_diagnostics},
        )

    expert_llm = ((graph_state.diagnostics.get("expert") or {}).get("llm") or {})
    if graph_state.execution_kind is ExecutionKind.DELEGATE and expert_llm.get("final_status") == "failed_after_retries":
        selected_agents = list(graph_state.selected_agents or [])
        expert_name = "education expert" if selected_agents == ["education"] else "emotional expert"
        raise LLMResponseError(
            f"supervisor {expert_name} failed after 3 attempts",
            diagnostics={"supervisor": supervisor_diagnostics},
        )


class SupervisorStage(PipelineStage):
    @property
    def stage_name(self) -> str:
        return "supervisor"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()

        if context.classification is None:
            return context

        current_state = CurrentState.from_dict(context.supervisor_state)
        message_type = _derive_message_type(context.request.user_input, current_state)

        # Шаг 7: одноагентная ветка с включёнными инструментами не грузит RAG
        # заранее — search_education агент вызывает сам, только если нужно.
        # _single_agent_applicable не зависит от patient_context, поэтому
        # решение можно принять раньше, чем обычно.
        use_agent_tools = _single_agent_applicable(context) and tools.agent_tools_enabled()

        (
            education_rag_context,
            education_rag_grounding_items,
            education_grounding_diagnostics,
            patient_context,
        ) = await _load_education_grounding(context, skip_rag=use_agent_tools)

        # Fallback: if education session is active but RAG returned nothing (e.g. query too short —
        # "давай", "да", "ок"), re-query with the saved education topic so the expert still has grounding.
        # Не для use_agent_tools: там RAG сознательно пропущен, а не "ничего не нашёл".
        if (
            not use_agent_tools
            and not education_rag_grounding_items
            and current_state.education_session_active
            and current_state.education_topic
        ):
            fallback_topic = str(current_state.education_topic).strip()
            if fallback_topic and fallback_topic != context.request.user_input.strip():
                logger.info(
                    "[supervisor] education grounding empty, retrying with education_topic patient=%d topic=%r",
                    context.request.patient_id,
                    fallback_topic,
                )
                (
                    education_rag_context,
                    education_rag_grounding_items,
                    education_grounding_diagnostics,
                    patient_context,
                ) = await _load_education_grounding(context, query_override=fallback_topic)

        context.education_rag_context = education_rag_context
        context.education_rag_grounding_items = education_rag_grounding_items

        strict_tier = bool(context.request.strict_model_tier)
        model_tier = _resolve_model_tier(
            context.classification.model_tier.value,
            current_state,
            strict=strict_tier,
            education_grounding_available=bool(education_rag_grounding_items),
        )
        # L0 поднял тревогу — на lite такой разговор вести нельзя. Только вверх:
        # понижать тир по сигналу тревоги мы не станем никогда.
        l0 = context.l0
        if not strict_tier and l0 is not None and l0.safety_level == "concern" and model_tier == "lite":
            logger.info(
                "[supervisor] L0 concern (%s) patient=%d — поднимаю тир lite→pro",
                l0.rule,
                context.request.patient_id,
            )
            model_tier = "pro"

        # Одноагентная ветка (шаг 4) живёт параллельно старой. С 2026-08-25
        # SAFETY тоже идёт сюда (см. docstring _single_agent_applicable —
        # настоящий L0-кризис до этой стадии не доходит). Сбой карточки внутри
        # ветки не откатывается на старую цепочку (см. docstring
        # _run_single_agent) — ветка отдаёт технический ответ сама.
        if _single_agent_applicable(context):
            return await _run_single_agent(
                context,
                current_state=current_state,
                message_type=message_type,
                model_tier=model_tier,
                strict_model_tier=strict_tier,
                patient_context=patient_context,
                education_rag_context=education_rag_context,
                education_grounding_diagnostics=education_grounding_diagnostics,
                started=started,
                use_agent_tools=use_agent_tools,
            )
        # Слои промпта [1] профиль и [3] окно строятся только под флагом —
        # при выключенном флаге промпт остаётся прежним байт-в-байт.
        profile_block = ""
        history_turns: list[dict[str, str]] = []
        if prompt_assembly.layers_enabled():
            profile_block = prompt_assembly.build_profile_layer(patient_context)
            history_turns = [
                {"role": item["role"], "content": item["content"]}
                for item in (patient_context.get("chat_history") or [])
                if isinstance(item, dict) and item.get("role") and item.get("content")
            ]

        graph_state = await run_first_module(
            FirstModuleInput(
                user_message=context.request.user_input,
                current_state=current_state,
                message_type=message_type,
                model_tier=model_tier,
                strict_model_tier=strict_tier,
                education_rag_context=education_rag_context,
                education_rag_grounding_items=education_rag_grounding_items,
                patient_gender=context.request.patient_gender,
                session_id=session_key(context.request.patient_id, context.request.thread_id),
                patient_id=context.request.patient_id,
                profile_block=profile_block,
                history=history_turns,
            )
        )

        updated_state = _build_updated_state(current_state, graph_state)
        before_state = current_state.to_dict()
        after_state = updated_state.to_dict()
        state_delta = _changed_state(before_state, after_state)

        supervisor_diagnostics = {
            "enabled": True,
            "request_type": context.classification.request_type.value,
            "message_type": message_type,
            "graph_path": list(graph_state.diagnostics.get("graph_path") or []),
            "intake": dict(graph_state.diagnostics.get("intake") or {}),
            "delegation": dict(graph_state.diagnostics.get("delegation") or {}),
            "expert": dict(graph_state.diagnostics.get("expert") or {}),
            "selected_agents": list(graph_state.selected_agents),
            "needs_clarification": bool(graph_state.needs_clarification),
            "execution_kind": graph_state.execution_kind.value if graph_state.execution_kind else None,
            "education_grounding": education_grounding_diagnostics,
            "prompt_layers": {
                "enabled": prompt_assembly.layers_enabled(),
                "profile_chars": len(profile_block),
                "window_turns": len(history_turns),
                "prefix_fingerprints": list(getattr(graph_state, "prefix_fingerprints", []) or []),
            },
            "state_delta": state_delta,
            "state_after": after_state,
            "llm_totals": {
                "tokens_input": graph_state.total_tokens_input,
                "tokens_output": graph_state.total_tokens_output,
                "latency_ms": graph_state.total_latency_ms,
                "account_ids": list(graph_state.account_ids),
                "actual_model_tiers": list(graph_state.actual_model_tiers),
            },
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

        _raise_if_failed(graph_state, supervisor_diagnostics)

        reply = str(graph_state.final_reply or "").strip()
        if not reply:
            raise LLMResponseError(
                "supervisor graph v2 returned empty reply",
                diagnostics={"supervisor": supervisor_diagnostics},
            )

        # intake_error непустой только на техническом сбое intake-карточки
        # (intake_execute_node в nodes.py) — final_reply там уже не
        # содержательный ответ, а заглушка «повтори сообщение». Кризисный
        # постфикс на такую заглушку дописывать нельзя, даже если
        # classification.request_type остался SAFETY.
        intake_validation = (graph_state.diagnostics.get("intake") or {}).get("validation") or {}
        if str(intake_validation.get("error") or "").strip():
            context.response_is_fallback_error = True

        education_cta: dict[str, Any] | None = None
        _expert = getattr(graph_state, "expert_card", None)
        if isinstance(_expert, EducationExpertCard) and _expert.cta_type == "lesson" and _expert.cta_target:
            education_cta = {
                "type": "lesson",
                "label": _expert.cta_label or "",
                "lesson_id": _expert.cta_target.get("lesson_id"),
                "lesson_code": _expert.cta_target.get("lesson_code"),
            }

        turn = SupervisorTurnResult(
            reply=reply,
            state_delta=state_delta,
            updated_state=updated_state,
            message_type=message_type,
            selected_agents=list(graph_state.selected_agents),
            used_pending_answer=False,
            needs_clarification=bool(graph_state.needs_clarification),
            diagnostics=supervisor_diagnostics,
            education_cta=education_cta,
        )

        context.supervisor_turn = turn
        context.supervisor_state = after_state
        context.response_draft = reply
        context.response_tokens_input = int(graph_state.total_tokens_input or 0)
        context.response_tokens_output = int(graph_state.total_tokens_output or 0)
        context.response_account_id = graph_state.account_ids[-1] if graph_state.account_ids else "SUPERVISOR"
        context.response_actual_model_tier = (
            graph_state.actual_model_tiers[-1] if graph_state.actual_model_tiers else context.classification.model_tier.value
        )
        context.diagnostics["supervisor"] = supervisor_diagnostics

        logger.info(
            "[supervisor] patient=%d execution=%s selected_agents=%s",
            context.request.patient_id,
            supervisor_diagnostics.get("execution_kind") or "-",
            ",".join(graph_state.selected_agents) or "-",
        )
        return context
