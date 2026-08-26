"""Supervisor Stage: одноагентная ветка (один структурный вызов вместо цепочки узлов)."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.llm import agent, memory_store, prompt_assembly, router_l0, safety_responses, tools
from app.llm.context_builder_optimized import build_context_bundle_optimized
from app.llm.pool import session_key
from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.supervisor import CurrentState, SupervisorTurnResult
from app.llm.supervisor.classification import detect_message_type

logger = logging.getLogger("gpt-support-llm.pipeline.supervisor")


def _derive_message_type(user_message: str, current_state: CurrentState) -> str:
    return detect_message_type(user_message, current_state)


def _resolve_model_tier(
    requested_tier: str,
    *,
    strict: bool,
    education_grounding_available: bool = False,
) -> str:
    """Upgrade lite→pro when education grounding is loaded.

    classify_request() knows nothing about supervisor state, so short follow-up
    messages get tier=lite. The agent's 11-field card reliably fails on
    GigaChat-2; a pro-tier upgrade prevents the 3-retry failure cascade.

    education_grounding_available=True means RAG found education content — the
    request will almost certainly need the fuller card.

    strict=True (researcher debug with forced tier) is never upgraded.
    """
    if strict or requested_tier != "lite":
        return requested_tier
    if education_grounding_available:
        return "pro"
    return requested_tier


def _changed_state(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed[key] = after.get(key)
    return changed


async def _load_education_grounding(
    context: PipelineContext,
    *,
    query_override: str | None = None,
    skip_rag: bool = False,
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Возвращает (education view, grounding items, диагностика, сырой контекст пациента).

    Сырой контекст нужен послойной сборке промпта: из него строятся стабильные
    слои [1] профиль и [3] окно диалога.

    ``skip_rag=True`` (инструменты включены): RAG-поиск не запускается вовсе —
    агент получит ``search_education`` как инструмент и сходит за материалами
    сам, только если реально понадобится. Остальные секции (витальные, история
    чата, устойчивые факты) собираются как обычно — ``build_context_bundle_optimized``
    гейтит RAG-блок по длине запроса (``len(query) >= 10``), поэтому пустой
    query достаточен, чтобы его пропустить, не трогая остальную сборку. НЕ через
    ``query_override=""``: пустая строка falsy и утекла бы в
    ``query_override or user_input``.
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


def _agent_intent_to_agents(intent: str) -> list[str]:
    """Намерение агента → список агентов в терминах диагностики, для сравнимости."""
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
    валидации), ход всё равно остаётся на этой ветке — без отката на 3-вызовную
    цепочку intake → delegation → expert. Такой откат раньше маскировал сбои
    схемы статистикой старой ветки и утраивал задержку хода (см.
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
            "[single_agent] patient=%d не отдал карточку (%s) — технический ответ",
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
        # Техническая заглушка, не содержательный ответ. Если request_type здесь
        # всё же SAFETY (карточка не разобралась именно на тревожном сообщении),
        # кризисный постфикс в pipeline.py дописывать нельзя.
        context.response_is_fallback_error = True
        context.response_tokens_input = run.tokens_in
        context.response_tokens_output = run.tokens_out
        context.response_account_id = run.account_id or "AGENT"
        context.response_actual_model_tier = model_tier
        context.diagnostics["supervisor"] = diagnostics
        return context

    reply_card = run.reply

    # Второй эшелон. L0 работает до вызова и ловит явные формулировки; агент
    # видит сообщение целиком и замечает то, что регулярки пропускают.
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

        # Ветка с включёнными инструментами не грузит RAG заранее —
        # search_education агент вызывает сам, только если нужно.
        use_agent_tools = tools.agent_tools_enabled()

        (
            education_rag_context,
            education_rag_grounding_items,
            education_grounding_diagnostics,
            patient_context,
        ) = await _load_education_grounding(context, skip_rag=use_agent_tools)

        context.education_rag_context = education_rag_context
        context.education_rag_grounding_items = education_rag_grounding_items

        strict_tier = bool(context.request.strict_model_tier)
        model_tier = _resolve_model_tier(
            context.classification.model_tier.value,
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
