from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _format_stage(stage: dict[str, Any]) -> str:
    name = str(stage.get("name") or "unknown")
    status = str(stage.get("status") or "unknown")
    latency_ms = stage.get("latency_ms")
    if latency_ms is None:
        return f"{name}: {status}."
    return f"{name}: {status}, {int(latency_ms)} мс."


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

            agent = supervisor.get("agent") or {}
            if agent.get("intent"):
                supervisor_items.append(f"Intent: {agent['intent']}.")
            if agent.get("technique_id") and str(agent["technique_id"]).strip() not in ("нет", ""):
                supervisor_items.append(f"Техника: {agent['technique_id']}.")
            if agent.get("safety_level") and agent["safety_level"] != "none":
                supervisor_items.append(f"Safety: {agent['safety_level']} ({agent.get('safety_kind') or 'none'}).")
            if agent.get("next_action") and str(agent["next_action"]).strip() not in ("нет", ""):
                supervisor_items.append(f"Следующее действие: {agent['next_action']}.")

            error = supervisor.get("error")
            if error:
                supervisor_items.append(f"Агент не отдал карточку: {error}.")

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
        stage_names = [str(stage.get("name") or "unknown") for stage in stages]
        if stage_names:
            pipeline_items.append("Этапы pipeline: " + " -> ".join(stage_names) + ".")

        errors = [stage for stage in stages if str(stage.get("status") or "") == "error"]
        if errors:
            pipeline_items.append("На этапе возникла ошибка: " + "; ".join(_format_stage(stage) for stage in errors[:2]))

    response_info = diagnostics.get("response") or {}
    response_source = str(response_info.get("source") or "").strip()
    if response_source == "supervisor":
        pipeline_items.append("Финальный ответ сформирован агентом.")
    elif response_source:
        pipeline_items.append(f"Финальный ответ сформирован через {response_source}.")

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

    return sections
