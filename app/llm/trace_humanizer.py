from __future__ import annotations

from typing import Any


# _as_list
def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


# _humanize_validation_status
def _humanize_validation_status(status: str | None) -> str | None:
    mapping = {
        "passed": "Ответ прошел валидацию без переписывания.",
        "rewritten": "Ответ был переписан после валидации.",
        "rewrite_failed": "Валидация запросила rewrite, но переписывание завершилось ошибкой.",
        "supervisor_draft_kept": "Supervisor-черновик оставили как есть, без отдельного rewrite после валидации.",
        "skipped_safety": "Для safety-ответа дополнительная валидация не запускалась.",
        "skipped_early_response": "Пайплайн завершился ранним ответом до валидации.",
        "skipped_no_response": "Валидация была пропущена, потому что не было черновика ответа.",
    }
    return mapping.get(str(status or "").strip())


# _format_stage
def _format_stage(stage: dict[str, Any]) -> str:
    name = str(stage.get("name") or "unknown")
    status = str(stage.get("status") or "unknown")
    latency_ms = stage.get("latency_ms")
    if latency_ms is None:
        return f"{name}: {status}."
    return f"{name}: {status}, {int(latency_ms)} мс."


# build_human_trace
def build_human_trace(diagnostics: dict[str, Any] | None) -> list[dict[str, Any]]:
    diagnostics = diagnostics or {}
    sections: list[dict[str, Any]] = []

    supervisor = diagnostics.get("supervisor") or {}
    supervisor_items: list[str] = []
    if supervisor:
        if supervisor.get("enabled"):
            message_type = supervisor.get("message_type")
            if message_type:
                supervisor_items.append(f"Supervisor определил тип хода: {message_type}.")

            goal_analysis = supervisor.get("goal_analysis") or supervisor.get("goal_extraction") or {}
            attempts_total = goal_analysis.get("attempts_total")
            succeeded_on_attempt = goal_analysis.get("succeeded_on_attempt")
            final_status = goal_analysis.get("final_status")
            if succeeded_on_attempt:
                supervisor_items.append(f"LLM goal analysis: success on attempt {succeeded_on_attempt}.")
            elif final_status == "failed_after_retries":
                supervisor_items.append(f"LLM goal analysis failed after {attempts_total or 3} attempts.")

            if goal_analysis.get("used") and goal_analysis.get("goal_status"):
                supervisor_items.append(f"LLM goal extraction reason: {goal_analysis['goal_status']}.")
            elif goal_analysis.get("used") and goal_analysis.get("reason"):
                supervisor_items.append(f"LLM goal extraction reason: {goal_analysis['reason']}.")

            if goal_analysis.get("used") and goal_analysis.get("goal"):
                supervisor_items.append(f"Goal выделила LLM: {goal_analysis['goal']}.")

            clarification_analysis = supervisor.get("clarification_analysis") or {}
            clarification_reason = clarification_analysis.get("clarification_reason") or goal_analysis.get(
                "clarification_reason"
            )
            if clarification_reason:
                supervisor_items.append(f"Clarification reason: {clarification_reason}.")

            response_mode = supervisor.get("response_mode")
            if response_mode:
                supervisor_items.append(f"Response mode: {response_mode}.")

            context_sufficiency = supervisor.get("context_sufficiency") or {}
            support_sufficient = context_sufficiency.get("support")
            plan_sufficient = context_sufficiency.get("plan")
            if support_sufficient is not None or plan_sufficient is not None:
                support_text = "sufficient" if support_sufficient else "insufficient"
                plan_text = "sufficient" if plan_sufficient else "insufficient"
                supervisor_items.append(
                    f"LLM decided context is {support_text} for support and {plan_text} for plan."
                )

            state_after = supervisor.get("state_after") or {}
            clarification_streak = state_after.get("clarification_streak")
            if clarification_streak:
                supervisor_items.append(f"Clarification streak: {clarification_streak}/5.")

            clarification_gate = (supervisor.get("turn_diagnostics") or {}).get("clarification_gate") or {}
            if clarification_gate.get("reason") == "generic_distress":
                supervisor_items.append("LLM распознала generic distress -> context clarification.")
            if clarification_gate.get("forced_by_cap"):
                supervisor_items.append("Clarification cap reached, so supervisor switched to best-effort help.")

            selected_agents = [str(item) for item in _as_list(supervisor.get("selected_agents")) if str(item).strip()]
            if selected_agents:
                supervisor_items.append("Подключенные expert-агенты: " + ", ".join(selected_agents) + ".")

            if supervisor.get("used_pending_answer"):
                supervisor_items.append("Короткий ответ был использован для slot-fill без полной переклассификации.")

            if supervisor.get("needs_clarification"):
                supervisor_items.append("Supervisor остановился на одном уточняющем вопросе перед делегированием.")

            llm_draft = supervisor.get("llm_draft") or {}
            if llm_draft.get("used"):
                supervisor_items.append("Финальную формулировку этого хода переписали через LLM.")
        else:
            reason = str(supervisor.get("reason") or "disabled")
            supervisor_items.append(f"Supervisor-path не использовался: {reason}.")

    if supervisor_items:
        sections.append({"title": "Supervisor", "items": supervisor_items})

    prompt = diagnostics.get("prompt") or {}
    prompt_items: list[str] = []
    selected_policy = prompt.get("selected_policy")
    if selected_policy:
        prompt_items.append(f"Выбран стиль ответа: {selected_policy}.")
    policy_reasons = _as_list(prompt.get("policy_reasons"))
    if policy_reasons:
        prompt_items.append("Причины выбора: " + ", ".join(str(x) for x in policy_reasons[:4]) + ".")
    if prompt_items:
        sections.append({"title": "Политика ответа", "items": prompt_items})

    pipeline_items: list[str] = []
    stages = _as_list(diagnostics.get("stages"))
    if stages:
        errors = [stage for stage in stages if str(stage.get("status") or "") == "error"]
        if errors:
            pipeline_items.append("На этапе возникла ошибка: " + "; ".join(_format_stage(stage) for stage in errors[:2]))
    patient_context = diagnostics.get("patient_context") or {}
    if patient_context.get("skipped"):
        pipeline_items.append(f"Context stage пропущен: {patient_context.get('reason')}.")
    intake = diagnostics.get("intake") or {}
    if intake.get("skipped"):
        pipeline_items.append(f"Intake stage пропущен: {intake.get('reason')}.")
    orchestration = diagnostics.get("orchestration") or {}
    if orchestration.get("skipped"):
        pipeline_items.append(f"Legacy orchestration пропущена: {orchestration.get('reason')}.")
    elif orchestration.get("enabled"):
        mode = orchestration.get("mode")
        if mode:
            pipeline_items.append(f"Legacy orchestration mode: {mode}.")
        route = orchestration.get("route") or {}
        selected_agents = [str(item) for item in _as_list(route.get("selected_agents")) if str(item).strip()]
        if selected_agents:
            pipeline_items.append("Legacy-агенты: " + ", ".join(selected_agents) + ".")
    validation = diagnostics.get("validation") or {}
    validation_status = _humanize_validation_status(validation.get("status"))
    if validation_status:
        pipeline_items.append(validation_status)
    if pipeline_items:
        sections.append({"title": "Пайплайн", "items": pipeline_items})

    memory = diagnostics.get("memory") or {}
    memory_items: list[str] = []
    reads = memory.get("reads") or {}
    st_count = int(reads.get("st_count") or 0)
    lt_count = int(reads.get("lt_count") or 0)
    if st_count or lt_count:
        memory_items.append(f"Прочитано из памяти: ST {st_count}, LT {lt_count}.")
    continuation = memory.get("continuation") or {}
    if continuation.get("used"):
        if continuation.get("session_constraint"):
            memory_items.append(
                f"Продолжили предыдущую ветку с учетом ограничения: {continuation['session_constraint']}."
            )
        else:
            memory_items.append("Короткий follow-up был понят как продолжение предыдущей ветки.")
    for item in _as_list(memory.get("proposed_st_entries")):
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if key and value:
            memory_items.append(f"В ST-memory записали: {key} = {value}.")
    for item in _as_list(memory.get("proposed_lt_entries")):
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if key and value:
            memory_items.append(f"В LT-memory предложили записать: {key} = {value}.")
    if memory_items:
        sections.append({"title": "Память", "items": memory_items})

    llm_call = diagnostics.get("llm_call") or {}
    llm_items: list[str] = []
    if llm_call.get("model"):
        llm_items.append(f"Модель: {llm_call['model']}.")
    if llm_call.get("tokens_input") is not None and llm_call.get("tokens_output") is not None:
        llm_items.append(
            f"Токены: input {int(llm_call.get('tokens_input') or 0)}, output {int(llm_call.get('tokens_output') or 0)}."
        )
    if llm_call.get("latency_ms") is not None:
        llm_items.append(f"Время вызова модели: {int(llm_call.get('latency_ms') or 0)} мс.")
    if llm_items:
        sections.append({"title": "Модель", "items": llm_items})

    return sections
