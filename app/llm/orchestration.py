from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import asyncio
import json
from pathlib import Path
import re
import time
import textwrap
import yaml

from app.llm.router import RequestType, RouterResult


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_prompt_label(agent_name: str) -> str:
    return {
        "psych_support": "РїСЃРёС…РѕР»РѕРіРёС‡РµСЃРєР°СЏ РїРѕРґРґРµСЂР¶РєР°",
        "education": "РѕР±СѓС‡РµРЅРёРµ",
        "routine": "СЂСѓС‚РёРЅР°",
    }.get(agent_name, agent_name)


_PROMPTS_DIR = Path(__file__).parent / "prompts"
_PROMPT_CACHE: dict[str, str] = {}


def load_orchestration_prompt(filename: str) -> str:
    if filename in _PROMPT_CACHE:
        return _PROMPT_CACHE[filename]
    text = (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()
    _PROMPT_CACHE[filename] = text
    return text


def _parse_llm_mapping(candidate: str) -> dict[str, object]:
    try:
        payload = json.loads(candidate)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    stripped = candidate.strip()
    inner = stripped[1:-1] if stripped.startswith("{") and stripped.endswith("}") else stripped
    yaml_fallback = textwrap.dedent(inner).strip()

    for attempt in (candidate, inner.strip(), yaml_fallback):
        if not attempt:
            continue
        try:
            payload = yaml.safe_load(attempt)
        except yaml.YAMLError:
            continue
        if isinstance(payload, dict):
            return payload

    raise ValueError("No JSON object found in LLM response")


def _extract_json_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced_match:
        return _parse_llm_mapping(fenced_match.group(1))
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return _parse_llm_mapping(stripped[start : end + 1])
    raise ValueError("No JSON object found in LLM response")


def _json_repair_prompt(*, stage: str, agent_name: str) -> str:
    if stage == "router":
        return (
            "Convert the previous assistant answer into a strict JSON object. "
            "Return JSON only, no markdown, no prose. "
            'Required keys: "selected_agents" (array of strings), "primary_agent" (string), '
            '"secondary_agents" (array of strings), "routing_reasons" (array of strings), '
            '"risk_flags" (array of strings), "why_not_selected" (object).'
        )
    if stage == "specialist":
        return (
            f'Convert the previous assistant answer into a strict JSON object for specialist "{agent_name}". '
            "Return JSON only, no markdown, no prose. "
            'Required keys: "agent", "status", "signals", "recommended_actions", "avoid", "draft", '
            '"notes_for_composer", "selected_context_sections", "cta_type", "cta_label", '
            '"cta_reason", "cta_target", "cta_soft_text".'
        )
    if stage == "composer":
        return (
            "Convert the previous assistant answer into a strict JSON object. "
            "Return JSON only, no markdown, no prose. "
            'Required keys: "status", "guidance_text", "blocks", "composition_rules", "draft_response".'
        )
    if stage == "critic":
        return (
            "Convert the previous assistant answer into a strict JSON object. "
            "Return JSON only, no markdown, no prose. "
            'Required keys: "status", "violations", "severity", "rewrite_required", '
            '"rewrite_reasons", "route_feedback", "critic_notes".'
        )
    return (
        "Convert the previous assistant answer into a strict JSON object. "
        "Return JSON only, no markdown, no prose."
    )


def _tokenize_grounding_text(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\b\w{4,}\b", text.lower(), flags=re.UNICODE)
        if token not in {"урок", "релевантный", "фрагмент", "если", "можно", "нужно", "только"}
    }


_UNGROUNDED_ACTION_PATTERNS = (
    "попробуй",
    "сделай",
    "создай",
    "избегай",
    "подыш",
    "дыхан",
    "медитац",
    "обстанов",
    "экран",
    "расслаб",
    "психолог",
    "обратись",
    "обратитесь",
    "обратиться",
)


@dataclass(slots=True)
class AgentTraceEvent:
    stage: str
    agent_name: str
    started_at: str
    latency_ms: int
    status: str
    decision: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    input_summary: str = ""
    selected_context_sections: list[str] = field(default_factory=list)
    prompt_chars: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    raw_output: dict[str, object] = field(default_factory=dict)
    normalized_output: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RouteDecision:
    selected_agents: list[str]
    primary_agent: str | None
    secondary_agents: list[str]
    routing_reasons: list[str]
    risk_flags: list[str]
    why_not_selected: dict[str, list[str]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SpecialistOutput:
    agent: str
    status: str
    signals: list[str]
    recommended_actions: list[str]
    avoid: list[str]
    draft: str
    notes_for_composer: list[str]
    selected_context_sections: list[str]
    cta_type: str = "none"
    cta_label: str = ""
    cta_reason: str = ""
    cta_target: dict[str, object] = field(default_factory=dict)
    cta_soft_text: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ComposerOutput:
    status: str
    guidance_text: str
    blocks: list[str]
    composition_rules: list[str]
    draft_response: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class CriticVerdict:
    status: str
    violations: list[str]
    severity: str
    rewrite_required: bool
    rewrite_reasons: list[str]
    route_feedback: list[str]
    critic_notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class FullLLMOrchestrationResult:
    final_response: str
    route: RouteDecision
    specialists: list[SpecialistOutput]
    composer: ComposerOutput
    critic: CriticVerdict
    trace: list[AgentTraceEvent]
    rewrite: dict[str, object]
    tokens_input: int
    tokens_output: int
    latency_ms: int


@dataclass(slots=True)
class SpecialistGroundingProbeResult:
    specialists: list[SpecialistOutput]
    trace: list[AgentTraceEvent]
    tokens_input: int
    tokens_output: int
    latency_ms: int


def _has_any_grounded_actions(specialists: list["SpecialistOutput"]) -> bool:
    return any(item.recommended_actions for item in specialists)


def _looks_like_ungrounded_action_response(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(pattern in lowered for pattern in _UNGROUNDED_ACTION_PATTERNS)


def _build_validation_only_response(specialists: list["SpecialistOutput"]) -> str:
    drafts: list[str] = []
    seen: set[str] = set()
    for item in specialists:
        draft = str(item.draft or "").strip()
        if not draft:
            continue
        key = draft.lower()
        if key in seen:
            continue
        seen.add(key)
        drafts.append(draft)
    if drafts:
        return " ".join(drafts)
    return "Похоже, сейчас тебе непросто."


def _postprocess_route_with_context(
    *,
    route: RouteDecision,
    rag_context: list[str] | None,
    rag_views: dict[str, list[str]] | None = None,
) -> RouteDecision:
    selected_agents = list(route.selected_agents)
    why_not_selected = dict(route.why_not_selected or {})
    routing_reasons = list(route.routing_reasons or [])
    has_explicit_routine_view = rag_views is not None and "routine" in rag_views

    if "routine" in selected_agents and has_explicit_routine_view and not _agent_rag_context(
        agent_name="routine",
        rag_context=rag_context,
        rag_views=rag_views,
    ):
        selected_agents = [agent for agent in selected_agents if agent != "routine"]
        why_not_selected["routine"] = list(why_not_selected.get("routine") or []) + ["no_routine_rag_view"]
        routing_reasons.append("routine_skipped_no_actionable_rag")

    if not selected_agents:
        if _agent_rag_context(agent_name="education", rag_context=rag_context, rag_views=rag_views):
            selected_agents = ["education"]
            why_not_selected["routine"] = list(why_not_selected.get("routine") or []) + ["fallback_to_education"]
            routing_reasons.append("fallback_to_education_context")
        elif "psych_support" in route.selected_agents:
            selected_agents = ["psych_support"]
            why_not_selected["routine"] = list(why_not_selected.get("routine") or []) + ["fallback_to_psych_support"]
            routing_reasons.append("fallback_to_psych_support")

    primary_agent = route.primary_agent
    if primary_agent not in selected_agents:
        primary_agent = selected_agents[0] if selected_agents else None

    secondary_agents = [agent for agent in selected_agents if agent != primary_agent]

    return RouteDecision(
        selected_agents=selected_agents,
        primary_agent=primary_agent,
        secondary_agents=secondary_agents,
        routing_reasons=routing_reasons,
        risk_flags=list(route.risk_flags or []),
        why_not_selected=why_not_selected,
    )


def analyze_rag_grounding(
    *,
    output: SpecialistOutput,
    rag_context: list[str] | None,
) -> dict[str, object]:
    rag_items = list(rag_context or [])
    if not rag_items:
        return {
            "rag_items_total": 0,
            "used_rag_indices": [],
            "ignored_rag_indices": [],
            "used_rag_items": [],
            "ignored_rag_items": [],
            "used_rag_count": 0,
            "grounding_status": "no_rag",
        }

    response_text = " ".join(
        [
            output.draft,
            *output.recommended_actions,
            *output.signals,
            *output.notes_for_composer,
        ]
    )
    response_tokens = _tokenize_grounding_text(response_text)
    used_rag_indices: list[int] = []
    for index, item in enumerate(rag_items):
        if response_tokens & _tokenize_grounding_text(item):
            used_rag_indices.append(index)

    return {
        "rag_items_total": len(rag_items),
        "used_rag_indices": used_rag_indices,
        "ignored_rag_indices": [index for index in range(len(rag_items)) if index not in used_rag_indices],
        "used_rag_items": [rag_items[index] for index in used_rag_indices],
        "ignored_rag_items": [item for index, item in enumerate(rag_items) if index not in used_rag_indices],
        "used_rag_count": len(used_rag_indices),
        "grounding_status": "used_rag" if used_rag_indices else "ignored_rag",
    }


def analyze_specialist_cta(
    *,
    output: SpecialistOutput,
    rag_grounding_items: list[dict[str, object]] | None,
) -> dict[str, object]:
    items = list(rag_grounding_items or [])
    if not output.cta_type or output.cta_type == "none":
        return {
            "cta_added": False,
            "cta_type": "none",
            "cta_target_found": False,
            "cta_matches_progress": True,
            "available_cta_types": sorted({str((item.get("cta") or {}).get("cta_type") or "none") for item in items}),
        }

    target = output.cta_target or {}
    matched_item = None
    for item in items:
        cta = item.get("cta") or {}
        cta_target = cta.get("cta_target") or {}
        if output.cta_type != cta.get("cta_type"):
            continue
        if output.cta_type == "lesson" and target.get("lesson_code") and target.get("lesson_code") == cta_target.get("lesson_code"):
            matched_item = item
            break
        if output.cta_type == "practice" and target.get("practice_id") and target.get("practice_id") == cta_target.get("practice_id"):
            matched_item = item
            break

    return {
        "cta_added": True,
        "cta_type": output.cta_type,
        "cta_target_found": matched_item is not None,
        "cta_matches_progress": matched_item is not None,
        "matched_lesson_code": (matched_item or {}).get("lesson_code"),
        "matched_cta_reason": ((matched_item or {}).get("cta") or {}).get("cta_reason"),
        "available_cta_types": sorted({str((item.get("cta") or {}).get("cta_type") or "none") for item in items}),
    }


async def _call_json_step(
    *,
    client,
    system_prompt: str,
    user_content: str,
    stage: str,
    agent_name: str,
    input_summary: str,
    selected_context_sections: list[str] | None = None,
) -> tuple[dict[str, object], AgentTraceEvent, int, int, int]:
    started = time.monotonic()
    raw_text, tokens_in, tokens_out, elapsed_ms = await client.call(
        [{"role": "user", "content": user_content}],
        system_prompt,
    )
    repaired = False
    original_raw_text = raw_text
    try:
        payload = _extract_json_object(raw_text)
    except ValueError:
        repair_prompt = _json_repair_prompt(stage=stage, agent_name=agent_name)
        repair_user = (
            "Previous assistant answer:\n"
            f"{raw_text}\n\n"
            "Rewrite it into the required JSON structure."
        )
        raw_text, retry_in, retry_out, retry_elapsed_ms = await client.call(
            [{"role": "user", "content": repair_user}],
            repair_prompt,
        )
        tokens_in += retry_in
        tokens_out += retry_out
        elapsed_ms += retry_elapsed_ms
        payload = _extract_json_object(raw_text)
        repaired = True
    trace = AgentTraceEvent(
        stage=stage,
        agent_name=agent_name,
        started_at=_utc_now(),
        latency_ms=elapsed_ms,
        status="ok",
        decision=str(payload.get("status") or payload.get("primary_agent") or payload.get("decision") or agent_name),
        reasons=list(payload.get("routing_reasons") or payload.get("signals") or payload.get("violations") or []),
        warnings=list(payload.get("risk_flags") or payload.get("route_feedback") or []),
        input_summary=input_summary[:200],
        selected_context_sections=list(selected_context_sections or []),
        prompt_chars=len(system_prompt) + len(user_content),
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        raw_output={
            "raw_text": raw_text,
            "json_repaired": repaired,
            "original_raw_text": original_raw_text if repaired else raw_text,
        },
        normalized_output=payload,
    )
    return payload, trace, tokens_in, tokens_out, elapsed_ms


def _context_snapshot_text(
    *,
    user_input: str,
    router_result: RouterResult,
    parser_mood: str | None,
    parser_domain_hints: list[str] | None,
    patient_summary_prompt: list[str] | None,
    rag_context: list[str] | None,
    rag_grounding_items: list[dict[str, object]] | None = None,
) -> str:
    summary_lines = "\n".join(f"- {item}" for item in (patient_summary_prompt or [])) or "- ???"
    rag_lines = "\n".join(f"- {item}" for item in (rag_context or [])) or "- ???"
    grounding_lines = "- ???"
    if rag_grounding_items:
        rendered: list[str] = []
        for item in rag_grounding_items:
            cta = item.get("cta") or {}
            practice = item.get("practice") or {}
            rendered.append(
                (
                    f"- chunk#{item.get('rag_index', 0)} "
                    f"lesson_code={item.get('lesson_code') or '-'} "
                    f"is_read={item.get('is_read')} "
                    f"is_completed={item.get('is_completed')} "
                    f"has_passed_test={item.get('has_passed_test')} "
                    f"practice_title={practice.get('title') or '-'} "
                    f"cta_hint={cta.get('cta_type') or 'none'} "
                    f"cta_reason={cta.get('cta_reason') or 'none'}"
                )
            )
        grounding_lines = "\n".join(rendered)
    hints = ", ".join(parser_domain_hints or []) or "-"
    return (
        f"?????? ????????:\n{user_input}\n\n"
        f"??????? request_type: {router_result.request_type.value}\n"
        f"??????? domain_hint: {router_result.domain_hint or '-'}\n"
        f"?????????? parser: {parser_mood or '-'}\n"
        f"????????? ??????? parser: {hints}\n\n"
        f"??????? ?????? ???????? ??? prompt:\n{summary_lines}\n\n"
        f"????????? ?? RAG/???? ??????:\n{rag_lines}\n\n"
        f"RAG CTA metadata:\n{grounding_lines}"
    )


def _agent_rag_context(
    *,
    agent_name: str,
    rag_context: list[str] | None,
    rag_views: dict[str, list[str]] | None = None,
) -> list[str]:
    view_items = list((rag_views or {}).get(agent_name) or [])
    if agent_name == "education":
        return view_items or list(rag_context or [])
    return view_items


def _specialist_context_snapshot(
    *,
    agent_name: str,
    user_input: str,
    router_result: RouterResult,
    parser_mood: str | None,
    parser_domain_hints: list[str] | None,
    patient_summary_prompt: list[str] | None,
    patient_summary_views: dict[str, list[str]] | None = None,
    rag_context: list[str] | None,
    rag_views: dict[str, list[str]] | None = None,
    rag_grounding_items: list[dict[str, object]] | None = None,
) -> tuple[str, list[str]]:
    specialist_summary = list((patient_summary_views or {}).get(agent_name) or patient_summary_prompt or [])
    if agent_name == "psych_support":
        practice_items = [
            item for item in (rag_grounding_items or [])
            if isinstance(item.get("practice"), dict) and item.get("practice")
        ]
        return (
            _context_snapshot_text(
                user_input=user_input,
                router_result=router_result,
                parser_mood=parser_mood,
                parser_domain_hints=parser_domain_hints,
                patient_summary_prompt=specialist_summary,
                rag_context=_agent_rag_context(
                    agent_name="psych_support",
                    rag_context=rag_context,
                    rag_views=rag_views,
                ),
                rag_grounding_items=practice_items,
            ),
            ["patient_summary_prompt", "practice_metadata"],
        )

    agent_rag_context = _agent_rag_context(
        agent_name=agent_name,
        rag_context=rag_context,
        rag_views=rag_views,
    )
    selected_sections = ["patient_summary_prompt", "rag_context"]
    metadata_items = rag_grounding_items
    if agent_name == "routine":
        selected_sections = ["patient_summary_prompt", "rag_view_routine"]
        metadata_items = None
    elif agent_name == "education":
        selected_sections = ["patient_summary_prompt", "rag_view_education"]

    return (
        _context_snapshot_text(
            user_input=user_input,
            router_result=router_result,
            parser_mood=parser_mood,
            parser_domain_hints=parser_domain_hints,
            patient_summary_prompt=specialist_summary,
            rag_context=agent_rag_context,
            rag_grounding_items=metadata_items,
        ),
        selected_sections,
    )


def _build_trace(
    *,
    stage: str,
    agent_name: str,
    started: float,
    status: str,
    decision: str,
    reasons: list[str] | None = None,
    warnings: list[str] | None = None,
    input_summary: str = "",
    selected_context_sections: list[str] | None = None,
    prompt_chars: int = 0,
    raw_output: dict[str, object] | None = None,
    normalized_output: dict[str, object] | None = None,
) -> AgentTraceEvent:
    return AgentTraceEvent(
        stage=stage,
        agent_name=agent_name,
        started_at=_utc_now(),
        latency_ms=int((time.monotonic() - started) * 1000),
        status=status,
        decision=decision,
        reasons=list(reasons or []),
        warnings=list(warnings or []),
        input_summary=input_summary,
        selected_context_sections=list(selected_context_sections or []),
        prompt_chars=prompt_chars,
        raw_output=dict(raw_output or {}),
        normalized_output=dict(normalized_output or {}),
    )


async def run_full_llm_orchestration(
    *,
    client,
    user_input: str,
    router_result: RouterResult,
    parser_mood: str | None,
    parser_domain_hints: list[str] | None,
    patient_summary_prompt: list[str] | None,
    patient_summary_views: dict[str, list[str]] | None = None,
    rag_context: list[str] | None,
    rag_views: dict[str, list[str]] | None = None,
    rag_grounding_items: list[dict[str, object]] | None = None,
) -> FullLLMOrchestrationResult:
    context_text = _context_snapshot_text(
        user_input=user_input,
        router_result=router_result,
        parser_mood=parser_mood,
        parser_domain_hints=parser_domain_hints,
        patient_summary_prompt=patient_summary_prompt,
        rag_context=rag_context,
    )
    total_tokens_in = 0
    total_tokens_out = 0
    total_latency_ms = 0
    trace: list[AgentTraceEvent] = []

    router_payload, router_trace, ti, to, lat = await _call_json_step(
        client=client,
        system_prompt=load_orchestration_prompt("orchestration_router.txt"),
        user_content=context_text,
        stage="router",
        agent_name="router",
        input_summary=user_input,
        selected_context_sections=["patient_summary_prompt"],
    )
    total_tokens_in += ti
    total_tokens_out += to
    total_latency_ms += lat
    trace.append(router_trace)

    route = RouteDecision(
        selected_agents=list(router_payload.get("selected_agents") or ["routine"]),
        primary_agent=str(router_payload.get("primary_agent") or "routine"),
        secondary_agents=list(router_payload.get("secondary_agents") or []),
        routing_reasons=list(router_payload.get("routing_reasons") or []),
        risk_flags=list(router_payload.get("risk_flags") or []),
        why_not_selected=dict(router_payload.get("why_not_selected") or {}),
    )
    route = _postprocess_route_with_context(
        route=route,
        rag_context=rag_context,
        rag_views=rag_views,
    )

    async def run_specialist(agent_name: str) -> tuple[SpecialistOutput, AgentTraceEvent, int, int, int]:
        prompt_file = f"orchestration_specialist_{agent_name}.txt"
        specialist_context_text, selected_sections = _specialist_context_snapshot(
            agent_name=agent_name,
            user_input=user_input,
            router_result=router_result,
            parser_mood=parser_mood,
            parser_domain_hints=parser_domain_hints,
            patient_summary_prompt=patient_summary_prompt,
            patient_summary_views=patient_summary_views,
            rag_context=rag_context,
            rag_views=rag_views,
            rag_grounding_items=rag_grounding_items,
        )
        payload, specialist_trace, sti, sto, slat = await _call_json_step(
            client=client,
            system_prompt=load_orchestration_prompt(prompt_file),
            user_content=specialist_context_text,
            stage="specialist",
            agent_name=agent_name,
            input_summary=user_input,
            selected_context_sections=selected_sections,
        )
        output = SpecialistOutput(
            agent=str(payload.get("agent") or agent_name),
            status=str(payload.get("status") or "ok"),
            signals=list(payload.get("signals") or []),
            recommended_actions=list(payload.get("recommended_actions") or []),
            avoid=list(payload.get("avoid") or []),
            draft=str(payload.get("draft") or ""),
            notes_for_composer=list(payload.get("notes_for_composer") or []),
            selected_context_sections=list(payload.get("selected_context_sections") or ["patient_summary_prompt"]),
            cta_type=str(payload.get("cta_type") or "none"),
            cta_label=str(payload.get("cta_label") or ""),
            cta_reason=str(payload.get("cta_reason") or ""),
            cta_target=dict(payload.get("cta_target") or {}),
            cta_soft_text=str(payload.get("cta_soft_text") or ""),
        )
        specialist_trace.normalized_output = output.to_dict()
        specialist_trace.decision = "specialist_json"
        return output, specialist_trace, sti, sto, slat

    specialist_results = await asyncio.gather(*[run_specialist(name) for name in route.selected_agents])
    specialists: list[SpecialistOutput] = []
    for output, specialist_trace, sti, sto, slat in specialist_results:
        specialists.append(output)
        trace.append(specialist_trace)
        total_tokens_in += sti
        total_tokens_out += sto
        total_latency_ms += slat

    specialists_json = json.dumps([item.to_dict() for item in specialists], ensure_ascii=False, indent=2)
    composer_user = (
        f"{context_text}\n\n"
        f"РњР°СЂС€СЂСѓС‚ РѕСЂРєРµСЃС‚СЂР°С‚РѕСЂР°:\n{json.dumps(route.to_dict(), ensure_ascii=False, indent=2)}\n\n"
        f"Р’С‹С…РѕРґС‹ specialist-Р°РіРµРЅС‚РѕРІ:\n{specialists_json}"
    )
    composer_payload, composer_trace, ti, to, lat = await _call_json_step(
        client=client,
        system_prompt=load_orchestration_prompt("orchestration_composer.txt"),
        user_content=composer_user,
        stage="composer",
        agent_name="composer",
        input_summary=user_input,
        selected_context_sections=["patient_summary_prompt", "rag_context"],
    )
    total_tokens_in += ti
    total_tokens_out += to
    total_latency_ms += lat
    composer = ComposerOutput(
        status=str(composer_payload.get("status") or "ok"),
        guidance_text=str(composer_payload.get("guidance_text") or ""),
        blocks=list(composer_payload.get("blocks") or []),
        composition_rules=list(composer_payload.get("composition_rules") or []),
        draft_response=str(composer_payload.get("draft_response") or ""),
    )
    if not _has_any_grounded_actions(specialists) and _looks_like_ungrounded_action_response(composer.draft_response):
        composer.draft_response = _build_validation_only_response(specialists)
        composer.blocks = ["acknowledgement"]
        composer.composition_rules = ["validation_only", "no_ungrounded_actions"]
        composer.guidance_text = "Composer fallback: removed ungrounded actions and kept validation-only response."
    composer_trace.normalized_output = composer.to_dict()
    trace.append(composer_trace)

    critic_user = (
        f"{context_text}\n\n"
        f"РњР°СЂС€СЂСѓС‚ РѕСЂРєРµСЃС‚СЂР°С‚РѕСЂР°:\n{json.dumps(route.to_dict(), ensure_ascii=False, indent=2)}\n\n"
        f"Р’С‹С…РѕРґС‹ specialist-Р°РіРµРЅС‚РѕРІ:\n{specialists_json}\n\n"
        f"Р§РµСЂРЅРѕРІРёРє РѕС‚РІРµС‚Р°:\n{composer.draft_response}"
    )
    critic_payload, critic_trace, ti, to, lat = await _call_json_step(
        client=client,
        system_prompt=load_orchestration_prompt("orchestration_critic.txt"),
        user_content=critic_user,
        stage="critic",
        agent_name="critic",
        input_summary=composer.draft_response,
        selected_context_sections=["final_response"],
    )
    total_tokens_in += ti
    total_tokens_out += to
    total_latency_ms += lat
    critic = CriticVerdict(
        status=str(critic_payload.get("status") or "pass"),
        violations=list(critic_payload.get("violations") or []),
        severity=str(critic_payload.get("severity") or "low"),
        rewrite_required=bool(critic_payload.get("rewrite_required")),
        rewrite_reasons=list(critic_payload.get("rewrite_reasons") or []),
        route_feedback=list(critic_payload.get("route_feedback") or []),
        critic_notes=list(critic_payload.get("critic_notes") or []),
    )
    critic_trace.normalized_output = critic.to_dict()
    trace.append(critic_trace)

    final_response = composer.draft_response.strip()
    rewrite_diag: dict[str, object] = {
        "triggered": critic.rewrite_required,
        "attempted": False,
        "status": "not_needed",
        "reasons": list(critic.rewrite_reasons),
        "latency_ms": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "initial_response_chars": len(final_response),
        "final_response_chars": len(final_response),
        "final_response_source": "composer",
        "attempts": 0,
        "post_validation_reasons": [],
    }

    if critic.rewrite_required:
        rewrite_user = (
            f"{context_text}\n\n"
            f"Р§РµСЂРЅРѕРІРёРє РѕС‚РІРµС‚Р°:\n{final_response}\n\n"
            f"Р—Р°РјРµС‡Р°РЅРёСЏ critic:\n{json.dumps(critic.to_dict(), ensure_ascii=False, indent=2)}"
        )
        rewrite_started = time.monotonic()
        rewritten_text, rti, rto, rlat = await client.call(
            [{"role": "user", "content": rewrite_user}],
            load_orchestration_prompt("orchestration_rewrite.txt"),
        )
        rewrite_trace = AgentTraceEvent(
            stage="rewrite",
            agent_name="rewrite",
            started_at=_utc_now(),
            latency_ms=rlat,
            status="ok",
            decision="rewrite",
            reasons=list(critic.rewrite_reasons),
            warnings=[],
            input_summary=final_response[:200],
            selected_context_sections=["final_response"],
            prompt_chars=len(rewrite_user),
            tokens_input=rti,
            tokens_output=rto,
            raw_output={"raw_text": rewritten_text},
            normalized_output={"rewritten_response": rewritten_text.strip()},
        )
        total_tokens_in += rti
        total_tokens_out += rto
        total_latency_ms += rlat
        trace.append(rewrite_trace)
        final_response = rewritten_text.strip()
        rewrite_diag.update(
            {
                "attempted": True,
                "status": "ok",
                "latency_ms": rlat,
                "tokens_input": rti,
                "tokens_output": rto,
                "final_response_chars": len(final_response),
                "final_response_source": "rewrite",
                "attempts": 1,
            }
        )

        critic_after_user = (
            f"{context_text}\n\n"
            f"РџРµСЂРµРїРёСЃР°РЅРЅС‹Р№ РѕС‚РІРµС‚:\n{final_response}\n\n"
            "РџСЂРѕРІРµСЂСЊ, РѕСЃС‚Р°Р»РёСЃСЊ Р»Рё РµС‰С‘ РЅР°СЂСѓС€РµРЅРёСЏ. РћС‚РІРµС‚СЊ JSON."
        )
        critic_after_payload, critic_after_trace, ti, to, lat = await _call_json_step(
            client=client,
            system_prompt=load_orchestration_prompt("orchestration_critic.txt"),
            user_content=critic_after_user,
            stage="critic_after_rewrite",
            agent_name="critic",
            input_summary=final_response,
            selected_context_sections=["final_response"],
        )
        total_tokens_in += ti
        total_tokens_out += to
        total_latency_ms += lat
        rewrite_diag["post_validation_reasons"] = list(critic_after_payload.get("violations") or [])
        critic_after_trace.normalized_output = critic_after_payload
        trace.append(critic_after_trace)

    return FullLLMOrchestrationResult(
        final_response=final_response,
        route=route,
        specialists=specialists,
        composer=composer,
        critic=critic,
        trace=trace,
        rewrite=rewrite_diag,
        tokens_input=total_tokens_in,
        tokens_output=total_tokens_out,
        latency_ms=total_latency_ms,
    )


async def run_specialist_grounding_probe(
    *,
    client,
    user_input: str,
    router_result: RouterResult,
    parser_mood: str | None,
    parser_domain_hints: list[str] | None,
    patient_summary_prompt: list[str] | None,
    patient_summary_views: dict[str, list[str]] | None = None,
    rag_context: list[str] | None,
    rag_views: dict[str, list[str]] | None = None,
    rag_grounding_items: list[dict[str, object]] | None = None,
    selected_agents: list[str] | None = None,
) -> SpecialistGroundingProbeResult:
    context_text = _context_snapshot_text(
        user_input=user_input,
        router_result=router_result,
        parser_mood=parser_mood,
        parser_domain_hints=parser_domain_hints,
        patient_summary_prompt=patient_summary_prompt,
        rag_context=rag_context,
        rag_grounding_items=rag_grounding_items,
    )
    agent_names = list(selected_agents or ["psych_support", "education", "routine"])
    total_tokens_in = 0
    total_tokens_out = 0
    total_latency_ms = 0

    async def run_specialist(agent_name: str) -> tuple[SpecialistOutput, AgentTraceEvent, int, int, int]:
        specialist_context_text, selected_sections = _specialist_context_snapshot(
            agent_name=agent_name,
            user_input=user_input,
            router_result=router_result,
            parser_mood=parser_mood,
            parser_domain_hints=parser_domain_hints,
            patient_summary_prompt=patient_summary_prompt,
            patient_summary_views=patient_summary_views,
            rag_context=rag_context,
            rag_views=rag_views,
            rag_grounding_items=rag_grounding_items,
        )
        specialist_rag_context = _agent_rag_context(
            agent_name=agent_name,
            rag_context=rag_context,
            rag_views=rag_views,
        )
        payload, specialist_trace, sti, sto, slat = await _call_json_step(
            client=client,
            system_prompt=load_orchestration_prompt(f"orchestration_specialist_{agent_name}.txt"),
            user_content=specialist_context_text,
            stage="specialist_probe",
            agent_name=agent_name,
            input_summary=user_input,
            selected_context_sections=selected_sections,
        )
        output = SpecialistOutput(
            agent=str(payload.get("agent") or agent_name),
            status=str(payload.get("status") or "ok"),
            signals=list(payload.get("signals") or []),
            recommended_actions=list(payload.get("recommended_actions") or []),
            avoid=list(payload.get("avoid") or []),
            draft=str(payload.get("draft") or ""),
            notes_for_composer=list(payload.get("notes_for_composer") or []),
            selected_context_sections=list(payload.get("selected_context_sections") or selected_sections),
            cta_type=str(payload.get("cta_type") or "none"),
            cta_label=str(payload.get("cta_label") or ""),
            cta_reason=str(payload.get("cta_reason") or ""),
            cta_target=dict(payload.get("cta_target") or {}),
            cta_soft_text=str(payload.get("cta_soft_text") or ""),
        )
        specialist_trace.normalized_output = {
            **output.to_dict(),
            "rag_grounding": analyze_rag_grounding(output=output, rag_context=specialist_rag_context),
            "cta_diagnostics": analyze_specialist_cta(output=output, rag_grounding_items=rag_grounding_items),
        }
        specialist_trace.decision = "specialist_probe_json"
        return output, specialist_trace, sti, sto, slat

    specialist_results = await asyncio.gather(*[run_specialist(name) for name in agent_names])
    specialists: list[SpecialistOutput] = []
    trace: list[AgentTraceEvent] = []
    for output, specialist_trace, sti, sto, slat in specialist_results:
        specialists.append(output)
        trace.append(specialist_trace)
        total_tokens_in += sti
        total_tokens_out += sto
        total_latency_ms += slat

    return SpecialistGroundingProbeResult(
        specialists=specialists,
        trace=trace,
        tokens_input=total_tokens_in,
        tokens_output=total_tokens_out,
        latency_ms=total_latency_ms,
    )
