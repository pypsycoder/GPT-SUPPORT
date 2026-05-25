from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

import pytest

from scripts.run_llm_eval import EvalCase, _build_markdown_report, _filter_cases, _write_workbook


def test_write_workbook_includes_orchestration_sheet_and_columns(tmp_path: Path):
    output_path = tmp_path / "eval.xlsx"
    results = [
        {
            "case_id": "case_1",
            "category": "mixed",
            "status": "PASS",
            "issues": [],
            "input_text": "text",
            "expected_policy": "sleep_support",
            "notes": "notes",
            "model_tier": "lite",
            "response": "response",
            "tokens_input": 10,
            "tokens_output": 5,
            "response_time_ms": 100,
            "diagnostics": {
                "prompt": {
                    "selected_policy": "sleep_support",
                    "policy_reasons": ["sleep_context"],
                    "available_sections": ["patient_summary"],
                    "included_sections": ["patient_summary_prompt"],
                },
                "classify": {
                    "request_type": "simple",
                    "router_domain": "sleep",
                    "effective_domain": "sleep",
                },
                "parser": {
                    "mood": "bad",
                    "domain_hints": ["sleep", "emotion"],
                },
                "patient_context": {
                    "rag": {
                        "backend": "pgvector",
                        "hit_count": 1,
                        "embedding_request_ms": 11,
                        "vector_search_ms": 9,
                    },
                    "rag_context": ["Фрагмент RAG 1", "Фрагмент RAG 2"],
                },
                "llm_call": {"latency_ms": 100},
                "summary": {"total_stage_latency_ms": 150, "fallback_points": []},
                "orchestration": {
                    "enabled": True,
                    "route": {
                        "primary_agent": "psych_support",
                        "secondary_agents": ["routine"],
                        "selected_agents": ["psych_support", "routine"],
                        "routing_reasons": ["emotion_signal"],
                        "risk_flags": [],
                    },
                    "critic": {
                        "status": "pass",
                        "violations": [],
                        "route_feedback": [],
                    },
                    "agent_trace": [
                        {
                            "stage": "router",
                            "agent_name": "router",
                            "status": "ok",
                            "decision": "psych_support",
                            "reasons": ["emotion_signal"],
                            "warnings": [],
                            "selected_context_sections": ["patient_summary_prompt"],
                            "latency_ms": 2,
                            "input_summary": "text",
                            "normalized_output": {"primary_agent": "psych_support"},
                        },
                        {
                            "stage": "specialist",
                            "agent_name": "psych_support",
                            "status": "ok",
                            "decision": "support_strategy",
                            "reasons": ["emotion_signal"],
                            "warnings": [],
                            "selected_context_sections": ["patient_summary_prompt"],
                            "latency_ms": 3,
                            "input_summary": "text",
                            "normalized_output": {"agent": "psych_support"},
                        },
                        {
                            "stage": "composer",
                            "agent_name": "composer",
                            "status": "ok",
                            "decision": "compose_guidance",
                            "reasons": [],
                            "warnings": [],
                            "selected_context_sections": ["patient_summary_prompt"],
                            "latency_ms": 1,
                            "input_summary": "text",
                            "prompt_chars": 120,
                            "normalized_output": {"status": "ok"},
                        },
                        {
                            "stage": "critic",
                            "agent_name": "critic",
                            "status": "ok",
                            "decision": "pass",
                            "reasons": [],
                            "warnings": [],
                            "selected_context_sections": ["final_response"],
                            "latency_ms": 1,
                            "input_summary": "response",
                            "normalized_output": {"status": "pass"},
                        }
                    ],
                },
                "shadow_validation": {
                    "enabled": True,
                    "triggered": True,
                    "reasons": ["food_advice"],
                    "critic_status": "pass",
                    "critic_violations": [],
                    "matches_critic": False,
                    "legacy_only_reasons": ["food_advice"],
                    "critic_only_reasons": [],
                },
                "rewrite": {
                    "attempted": True,
                    "status": "ok",
                    "reasons": ["template_reassurance"],
                    "latency_ms": 15,
                    "tokens_input": 4,
                    "tokens_output": 2,
                    "attempts": 1,
                    "initial_response_chars": 20,
                    "final_response_chars": 18,
                    "final_response_source": "rewrite",
                    "post_validation_reasons": [],
                },
            },
        }
    ]

    _write_workbook(results, output_path, patient_id=1)

    wb = load_workbook(output_path)
    assert "Orchestration" in wb.sheetnames
    assert "Timeline" in wb.sheetnames
    cases_ws = wb["Cases"]
    cases_headers = [cell.value for cell in cases_ws[1]]
    assert "orch_primary_agent" in cases_headers
    assert "critic_status" in cases_headers
    assert "shadow_triggered" in cases_headers
    assert "shadow_matches_critic" in cases_headers

    orch_ws = wb["Orchestration"]
    orch_headers = [cell.value for cell in orch_ws[1]]
    assert "trace_stage" in orch_headers
    assert "trace_normalized_output_json" in orch_headers
    assert "shadow_triggered" in orch_headers
    assert orch_ws["A2"].value == "case_1"

    timeline_ws = wb["Timeline"]
    timeline_headers = [cell.value for cell in timeline_ws[1]]
    assert "step_no" in timeline_headers
    assert "step_label" in timeline_headers
    assert "details_json" in timeline_headers
    assert timeline_ws["A2"].value == "case_1"
    assert timeline_ws["D2"].value == 1
    assert timeline_ws["E2"].value == "prompt"
    timeline_labels = [cell.value for cell in timeline_ws["E"]]
    assert "shadow_validator" in timeline_labels


def test_filter_cases_returns_single_requested_case():
    cases = [
        EvalCase("case_a", "general", "text a", None, [], [], ""),
        EvalCase("case_b", "general", "text b", None, [], [], ""),
    ]

    filtered = _filter_cases(cases, "case_b")

    assert [item.case_id for item in filtered] == ["case_b"]


def test_filter_cases_raises_for_unknown_case():
    cases = [EvalCase("case_a", "general", "text a", None, [], [], "")]

    with pytest.raises(RuntimeError, match="Case 'missing_case' not found"):
        _filter_cases(cases, "missing_case")


def test_build_markdown_report_includes_case_timeline():
    results = [
        {
            "case_id": "case_1",
            "category": "mixed",
            "status": "PASS",
            "issues": [],
            "input_text": "text",
            "expected_policy": "sleep_support",
            "notes": "notes",
            "model_tier": "lite",
            "response": "response",
            "tokens_input": 10,
            "tokens_output": 5,
            "response_time_ms": 100,
            "diagnostics": {
                "prompt": {
                    "selected_policy": "sleep_support",
                    "policy_reasons": ["sleep_context"],
                    "included_sections": ["patient_summary_prompt"],
                },
                "classify": {},
                "patient_context": {
                    "rag": {"backend": "pgvector", "attempted": True, "hit_count": 1},
                    "rag_context": ["RAG text 1"],
                },
                "summary": {"total_stage_latency_ms": 150},
                "llm_call": {"latency_ms": 100},
                "orchestration": {
                    "enabled": True,
                    "mode": "llm_full",
                    "route": {
                        "selected_agents": ["psych_support", "routine"],
                        "primary_agent": "psych_support",
                    },
                    "critic": {"status": "pass"},
                    "agent_trace": [
                        {
                            "stage": "router",
                            "agent_name": "router",
                            "status": "ok",
                            "decision": "psych_support",
                            "reasons": ["emotion_signal"],
                            "warnings": [],
                            "selected_context_sections": ["patient_summary_prompt"],
                            "latency_ms": 2,
                            "normalized_output": {"primary_agent": "psych_support"},
                        }
                    ],
                },
                "rewrite": {
                    "attempted": True,
                    "status": "ok",
                    "reasons": ["template_reassurance"],
                    "latency_ms": 15,
                    "tokens_input": 4,
                    "tokens_output": 2,
                    "attempts": 1,
                    "initial_response_chars": 20,
                    "final_response_chars": 18,
                    "final_response_source": "rewrite",
                    "post_validation_reasons": [],
                },
            },
        }
    ]

    report = _build_markdown_report(results, generated_at="2026-04-05 11:30:00", patient_id=1)

    assert "#### case_1" in report
    assert "**RAG Context**" in report
    assert "1. RAG text 1" in report
    assert "**Timeline**" in report
    assert "1. `prompt` / `prompt_builder`" in report
    assert "2. `rag_retrieval` / `rag`" in report
    assert "3. `orchestrator` / `router`" in report
    assert "```json" in report
