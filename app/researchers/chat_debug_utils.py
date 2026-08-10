from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.llm.router import ModelTier, RouterResult


def apply_forced_model_tier(router_result: RouterResult, forced_tier: str | None) -> RouterResult:
    value = str(forced_tier or "").strip().lower()
    if not value:
        return router_result
    try:
        tier = ModelTier(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный model tier. Допустимо: lite, pro, max") from exc
    return RouterResult(
        request_type=router_result.request_type,
        model_tier=tier,
        domain_hint=router_result.domain_hint,
        priority=router_result.priority,
    )


def next_debug_report_path(reports_dir: Path, now: datetime | None = None) -> Path:
    current = now or datetime.now()
    base_name = current.strftime("%Y.%m.%d_%H.%M")
    candidate = reports_dir / f"{base_name}.md"
    suffix = 1

    while candidate.exists():
        candidate = reports_dir / f"{base_name}_{suffix:02d}.md"
        suffix += 1

    return candidate


def _format_router_card_markdown(router_card: dict[str, Any] | None, graph_path: list[Any] | None) -> str:
    supervisor = dict(router_card or {})
    intake = dict(supervisor.get("intake") or {})
    delegation = dict(supervisor.get("delegation") or {})
    expert = dict(supervisor.get("expert") or {})
    lines: list[str] = []

    if graph_path:
        path_items = [str(item).strip() for item in graph_path if str(item).strip()]
        if path_items:
            lines.append(f"- Path: {' -> '.join(path_items)}")

    intake_card = dict(intake.get("card") or {})
    if intake_card:
        lines.append("- Intake:")
        for key, label in [
            ("problem", "Проблема"),
            ("context", "Контекст"),
            ("needs_clarification", "Нужно уточнение"),
            ("question", "Вопрос"),
            ("ready_to_delegate", "Готово к передаче"),
            ("rationale", "Обоснование"),
        ]:
            value = intake_card.get(key)
            if value:
                lines.append(f"  - {label}: {value}")

    delegation_card = dict(delegation.get("card") or {})
    if delegation_card:
        lines.append("- Delegation:")
        for key, label in [("expert", "Эксперт"), ("task", "Задача"), ("rationale", "Обоснование")]:
            value = delegation_card.get(key)
            if value:
                lines.append(f"  - {label}: {value}")

    expert_card = dict(expert.get("card") or {})
    if expert_card:
        lines.append("- Expert:")
        for key, label in [
            ("support", "Поддержка"),
            ("step_now", "Шаг сейчас"),
            ("follow_up", "Уточнение после помощи"),
            ("needs_more_info", "Нужно ли уточнение"),
            ("explanation", "Объяснение"),
            ("cta_type", "CTA тип"),
            ("cta_label", "CTA заголовок"),
            ("cta_target", "CTA target"),
            ("rationale", "Обоснование"),
        ]:
            value = expert_card.get(key)
            if value:
                lines.append(f"  - {label}: {value}")

    return "\n".join(lines) if lines else "_Нет данных graph v2._"


def _format_human_trace_markdown(human_trace: list[dict[str, Any]] | None) -> str:
    sections = list(human_trace or [])
    if not sections:
        return "_Нет human trace._"

    lines: list[str] = []
    for section in sections:
        title = str(section.get("title") or "Trace").strip() or "Trace"
        lines.append(f"### {title}")
        items = list(section.get("items") or [])
        if not items:
            lines.append("- _Пусто_")
        else:
            for item in items:
                lines.append(f"- {str(item)}")
        lines.append("")

    return "\n".join(lines).strip()


def _format_json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def build_debug_report_markdown(payload: dict[str, Any]) -> str:
    turns = list(payload.get("turns") or [])
    lines: list[str] = [
        "# Researcher Debug Report",
        "",
        f"- Сохранено: {payload.get('saved_at') or payload.get('exported_at') or datetime.now().isoformat()}",
        f"- Session ID: {payload.get('session_id') or '-'}",
        f"- Thread ID: {payload.get('thread_id') or '-'}",
        f"- Patient ID: {payload.get('patient_id') or '-'}",
        f"- Пациент: {payload.get('patient_label') or '-'}",
        f"- Export scope: {payload.get('export_scope') or '-'}",
        "",
    ]

    for turn in turns:
        turn_number = turn.get("turn_number") or "?"
        diagnostics_json = dict(turn.get("diagnostics_json") or {})
        supervisor = dict(diagnostics_json.get("supervisor") or {})
        graph_path = supervisor.get("graph_path") or []
        lines.extend(
            [
                f"# Ход {turn_number}",
                "",
                "## Пациент",
                str(turn.get("user_message") or ""),
                "",
                "## Graph",
                _format_router_card_markdown(supervisor, graph_path),
                "",
                "## Бот",
                str(turn.get("assistant_reply") or ""),
                "",
                "## Trace",
                _format_human_trace_markdown(turn.get("human_trace") or []),
                "",
                "## Debug",
                "### State before",
                _format_json_block(turn.get("state_before") or {}),
                "",
                "### State after",
                _format_json_block(turn.get("state_after") or {}),
                "",
                "### Diagnostics",
                _format_json_block(diagnostics_json),
                "",
            ]
        )

    if payload.get("current_supervisor_state") is not None:
        lines.extend(
            [
                "# Текущее состояние supervisor",
                "",
                _format_json_block(payload.get("current_supervisor_state") or {}),
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


__all__ = [
    "apply_forced_model_tier",
    "build_debug_report_markdown",
    "next_debug_report_path",
]
