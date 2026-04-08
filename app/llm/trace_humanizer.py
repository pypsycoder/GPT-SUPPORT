from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return []


def _append(items: list[str], text: str | None) -> None:
    if text:
        items.append(text)


def build_human_trace(diagnostics: dict[str, Any] | None) -> list[dict[str, Any]]:
    diagnostics = diagnostics or {}
    sections: list[dict[str, Any]] = []

    classify = diagnostics.get("classify") or {}
    classify_items: list[str] = []
    request_type = classify.get("request_type")
    if request_type:
        classify_items.append(f"Оркестратор определил тип сообщения: {request_type}.")
    domain = classify.get("effective_domain") or classify.get("domain_hint")
    if domain:
        classify_items.append(f"Основная тема запроса: {domain}.")
    if classify.get("red_flags"):
        classify_items.append("В запросе замечены сигналы безопасности, их проверили отдельно.")
    if classify_items:
        sections.append({"title": "Понимание запроса", "items": classify_items})

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

    orchestration = diagnostics.get("orchestration") or {}
    orchestration_items: list[str] = []
    if orchestration.get("enabled"):
        mode = orchestration.get("mode")
        route = orchestration.get("route") or {}
        selected_agents = _as_list(route.get("selected_agents"))
        primary_agent = route.get("primary_agent")
        if mode:
            orchestration_items.append(f"Режим оркестрации: {mode}.")
        if selected_agents:
            orchestration_items.append(
                "Подключенные агенты: " + ", ".join(str(x) for x in selected_agents) + "."
            )
        if primary_agent:
            orchestration_items.append(f"Главный агент для ответа: {primary_agent}.")
        for specialist in _as_list(orchestration.get("specialists")):
            agent = str(specialist.get("agent") or "").strip()
            draft = str(specialist.get("draft") or "").strip()
            actions = _as_list(specialist.get("recommended_actions"))
            cta_type = str(specialist.get("cta_type") or "").strip()
            parts: list[str] = []
            if draft:
                parts.append(f"черновик: {draft}")
            if actions:
                parts.append("действия: " + ", ".join(str(x) for x in actions[:2]))
            if cta_type and cta_type != "none":
                parts.append(f"CTA: {cta_type}")
            if agent and parts:
                orchestration_items.append(f"Агент {agent}: " + "; ".join(parts) + ".")
        rewrite = orchestration.get("rewrite") or {}
        if rewrite.get("applied"):
            orchestration_items.append("Критик попросил переписать ответ перед финальной отправкой.")
    if orchestration_items:
        sections.append({"title": "Агенты", "items": orchestration_items})

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
