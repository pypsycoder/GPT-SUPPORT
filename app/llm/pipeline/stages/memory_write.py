"""
Memory Write Stage - build memory candidates.
"""

from __future__ import annotations

import logging
import time

from app.llm.memory import (
    MemoryCandidate,
    MemoryScope,
    MemoryWriterContext,
    build_lt_entry,
    build_st_entry,
    decide_memory_write,
)
from app.llm.pipeline.types import PipelineContext, PipelineStage

logger = logging.getLogger("gpt-support-llm.pipeline.memory_write")


def _normalize_session_token(value: str | None) -> str:
    return str(value or "").strip() or "default_session"


def _normalize_thread_token(value: str | None) -> str:
    return str(value or "").strip() or "default_thread"


def _build_memory_candidates(
    *,
    patient_id: int,
    session_id: str | None,
    thread_id: str | None,
    parser_mood: str | None,
    intake_primary_problem: str | None,
    intake_intent: str | None,
    effective_domain: str | None,
    selected_policy: str,
    route_primary_agent: str | None,
    rag_grounding_items: list[dict[str, object]] | None,
) -> list[MemoryCandidate]:
    candidates: list[MemoryCandidate] = []

    def add_candidate(
        *,
        candidate_id: str,
        source_layer: str,
        candidate_type: str,
        key: str,
        value: object,
        evidence: list[str],
    ) -> None:
        candidates.append(
            MemoryCandidate(
                candidate_id=candidate_id,
                source_layer=source_layer,
                candidate_type=candidate_type,
                key=key,
                value=value,
                patient_id=patient_id,
                session_id=session_id,
                thread_id=thread_id,
                memory_scope=MemoryScope.ST,
                evidence=evidence,
            )
        )

    if parser_mood and parser_mood != "unknown":
        add_candidate(
            candidate_id="memory_cand_parser_mood",
            source_layer="clarifier",
            candidate_type="context_fact",
            key="context_fact",
            value=f"mood:{parser_mood}",
            evidence=[f"parser mood={parser_mood}"],
        )

    current_problem_value = intake_primary_problem or effective_domain
    if current_problem_value:
        add_candidate(
            candidate_id="memory_cand_current_problem",
            source_layer="router",
            candidate_type="current_problem",
            key="current_problem",
            value=current_problem_value,
            evidence=[
                f"intake_primary_problem={intake_primary_problem}"
                if intake_primary_problem
                else f"effective_domain={effective_domain}"
            ],
        )

    current_intent_value = intake_intent or selected_policy
    if current_intent_value:
        add_candidate(
            candidate_id="memory_cand_current_intent",
            source_layer="router",
            candidate_type="current_intent",
            key="current_intent",
            value=current_intent_value,
            evidence=[
                f"intake_patient_intent={intake_intent}"
                if intake_intent
                else f"selected_policy={selected_policy}"
            ],
        )

    if route_primary_agent:
        add_candidate(
            candidate_id="memory_cand_active_help_mode",
            source_layer="router",
            candidate_type="active_help_mode",
            key="active_help_mode",
            value=route_primary_agent,
            evidence=[f"primary_agent={route_primary_agent}"],
        )

    for index, item in enumerate(rag_grounding_items or []):
        lesson_code = str(item.get("lesson_code") or "").strip()
        if not lesson_code or not item.get("has_passed_test"):
            continue
        candidates.append(
            MemoryCandidate(
                candidate_id=f"memory_cand_progress_passed_{index}",
                source_layer="progress",
                candidate_type="progress_event",
                key="stable_progress_fact",
                value=f"lesson_passed:{lesson_code}",
                patient_id=patient_id,
                session_id=session_id,
                thread_id=thread_id,
                memory_scope=MemoryScope.LT,
                evidence=[f"rag grounding shows passed test for {lesson_code}"],
                policy_hint="progress_event",
            )
        )

    return candidates


class MemoryWriteStage(PipelineStage):
    """Stage 6: build ST/LT memory write candidates."""

    @property
    def stage_name(self) -> str:
        return "memory_write"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()
        session_id = _normalize_session_token(context.request.session_id)
        thread_id = _normalize_thread_token(context.request.thread_id)
        context.diagnostics.setdefault("memory", {})

        supervisor_state = dict(context.supervisor_state or {})
        supervisor_selected_agents = list((context.supervisor_turn.selected_agents if context.supervisor_turn else []) or [])

        parser_mood = context.diagnostics.get("parser", {}).get("mood")
        intake_primary_problem = context.intake_result.primary_problem if context.intake_result else supervisor_state.get("goal")
        intake_intent = context.intake_result.patient_intent if context.intake_result else supervisor_state.get("intent")
        effective_domain = context.classification.domain_hint or supervisor_state.get("domain")
        selected_policy = str(supervisor_state.get("intent") or "default_support")
        route_primary_agent = None

        if supervisor_selected_agents:
            route_primary_agent = supervisor_selected_agents[0]
        elif context.orchestration_result and hasattr(context.orchestration_result, "route"):
            route_primary_agent = context.orchestration_result.route.primary_agent

        rag_grounding_items = context.patient_context.get("rag_grounding_items", []) if context.patient_context else []
        memory_candidates = _build_memory_candidates(
            patient_id=context.request.patient_id,
            session_id=session_id,
            thread_id=thread_id,
            parser_mood=parser_mood,
            intake_primary_problem=intake_primary_problem,
            intake_intent=intake_intent,
            effective_domain=effective_domain,
            selected_policy=selected_policy,
            route_primary_agent=route_primary_agent,
            rag_grounding_items=rag_grounding_items,
        )

        memory_writer_context = MemoryWriterContext()
        memory_write_decisions = [
            decide_memory_write(candidate, context=memory_writer_context)
            for candidate in memory_candidates
        ]

        proposed_st_entries = []
        proposed_lt_entries = []
        for index, decision_dict in enumerate(memory_write_decisions, start=1):
            candidate_id = decision_dict.candidate_id
            candidate = next((item for item in memory_candidates if item.candidate_id == candidate_id), None)
            if candidate is None or decision_dict.decision != "write":
                continue
            if decision_dict.target_memory == MemoryScope.ST.value:
                proposed_st_entries.append(
                    build_st_entry(candidate, decision_dict, memory_id=f"st_auto_{index}").to_dict()
                )
            elif decision_dict.target_memory == MemoryScope.LT.value:
                proposed_lt_entries.append(
                    build_lt_entry(candidate, decision_dict, memory_id=f"lt_auto_{index}").to_dict()
                )

        context.diagnostics["memory"]["candidates"] = [candidate.to_dict() for candidate in memory_candidates]
        context.diagnostics["memory"]["write_decisions"] = [decision.to_dict() for decision in memory_write_decisions]
        context.diagnostics["memory"]["proposed_st_entries"] = proposed_st_entries
        context.diagnostics["memory"]["proposed_lt_entries"] = proposed_lt_entries
        context.diagnostics["memory"]["latency_ms"] = int((time.monotonic() - started) * 1000)

        logger.info(
            "[memory_write] patient=%d candidates=%d st_entries=%d lt_entries=%d",
            context.request.patient_id,
            len(memory_candidates),
            len(proposed_st_entries),
            len(proposed_lt_entries),
        )
        return context
