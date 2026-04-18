from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _humanize_validation_status(status: str | None) -> str | None:
    mapping = {
        "passed": "Ответ прошел валидацию без переписывания.",
        "rewritten": "Ответ был переписан после валидации.",
        "rewrite_failed": "Валидация запросила rewrite, но переписывание завершилось ошибкой.",
        "supervisor_draft_kept": "Финальный ответ был взят напрямую из supervisor graph v2.",
        "skipped_safety": "Для safety-ответа дополнительная валидация не запускалась.",
        "skipped_early_response": "Пайплайн завершился ранним ответом до валидации.",
        "skipped_no_response": "Валидация была пропущена, потому что не было черновика ответа.",
    }
    return mapping.get(str(status or "").strip())


def _format_stage(stage: dict[str, Any]) -> str:
    name = str(stage.get("name") or "unknown")
    status = str(stage.get("status") or "unknown")
    latency_ms = stage.get("latency_ms")
    if latency_ms is None:
        return f"{name}: {status}."
    return f"{name}: {status}, {int(latency_ms)} мс."


def _append_llm_attempts(items: list[str], label: str, llm: dict[str, Any] | None) -> None:
    llm = dict(llm or {})
    if not llm:
        return

    succeeded_on_attempt = llm.get("succeeded_on_attempt")
    attempts_total = int(llm.get("attempts_total") or 0)
    failures = _as_list(llm.get("failures"))
    retry_count = len(failures)

    if succeeded_on_attempt:
        items.append(f"{label}: success on attempt {int(succeeded_on_attempt)}.")
        if retry_count:
            items.append(f"{label}: retries before success = {retry_count}.")
    elif llm.get("final_status") == "failed_after_retries":
        items.append(f"{label} failed after {attempts_total or 3} attempts.")

    for failure in failures:
        attempt = failure.get("attempt")
        error_type = str(failure.get("error_type") or "Error").strip()
        error_message = str(failure.get("error_message") or "").strip()
        raw_excerpt = str(failure.get("raw_excerpt") or "").strip()
        line = f"{label} retry"
        if attempt:
            line += f" #{attempt}"
        line += f": {error_type}"
        if error_message:
            line += f" - {error_message}"
        if raw_excerpt:
            line += f" | raw: {raw_excerpt}"
        line += "."
        items.append(line)


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

            graph_path = _as_list(supervisor.get("graph_path"))
            if graph_path:
                supervisor_items.append("Graph path: " + " -> ".join(str(item) for item in graph_path) + ".")

            intake = supervisor.get("intake") or {}
            intake_card = intake.get("card") or {}
            _append_llm_attempts(supervisor_items, "Intake analysis", intake.get("llm"))
            if intake_card.get("problem"):
                supervisor_items.append(f"Проблема: {intake_card['problem']}.")
            if intake_card.get("needs_clarification"):
                supervisor_items.append(f"Нужно уточнение: {intake_card['needs_clarification']}.")
            if intake_card.get("ready_to_delegate"):
                supervisor_items.append(f"Готово к передаче: {intake_card['ready_to_delegate']}.")

            delegation = supervisor.get("delegation") or {}
            delegation_card = delegation.get("card") or {}
            _append_llm_attempts(supervisor_items, "Delegation analysis", delegation.get("llm"))
            if delegation_card.get("expert"):
                supervisor_items.append(f"Эксперт: {delegation_card['expert']}.")
            if delegation_card.get("task"):
                supervisor_items.append(f"Задача эксперта: {delegation_card['task']}.")

            expert = supervisor.get("expert") or {}
            expert_card = expert.get("card") or {}
            _append_llm_attempts(supervisor_items, "Emotional expert", expert.get("llm"))
            if expert_card.get("step_now"):
                supervisor_items.append(f"Шаг сейчас: {expert_card['step_now']}.")

            selected_agents = [str(item) for item in _as_list(supervisor.get("selected_agents")) if str(item).strip()]
            if selected_agents:
                supervisor_items.append("Подключенные expert-агенты: " + ", ".join(selected_agents) + ".")
        else:
            reason = str(supervisor.get("reason") or "disabled")
            supervisor_items.append(f"Supervisor-path не использовался: {reason}.")

    if supervisor_items:
        sections.append({"title": "Supervisor", "items": supervisor_items})

    pipeline_items: list[str] = []
    stages = _as_list(diagnostics.get("stages"))
    if stages:
        errors = [stage for stage in stages if str(stage.get("status") or "") == "error"]
        if errors:
            pipeline_items.append("На этапе возникла ошибка: " + "; ".join(_format_stage(stage) for stage in errors[:2]))

    patient_context = diagnostics.get("patient_context") or {}
    if patient_context.get("skipped"):
        pipeline_items.append(f"Context stage пропущен: {patient_context.get('reason')}.")
    intake_stage = diagnostics.get("intake") or {}
    if intake_stage.get("skipped"):
        pipeline_items.append(f"Intake stage пропущен: {intake_stage.get('reason')}.")
    orchestration = diagnostics.get("orchestration") or {}
    if orchestration.get("skipped"):
        pipeline_items.append(f"Legacy orchestration пропущена: {orchestration.get('reason')}.")

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
    for item in _as_list(memory.get("proposed_st_entries")):
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if key and value:
            memory_items.append(f"В ST-memory записали: {key} = {value}.")
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
