"""Phase 3 test: verify technique library integration with real LLM calls.

Tests 6 scenarios from the sprint plan matrix.
Runs directly against run_first_module — no DB required.

Usage: py scripts/test_phase3_techniques.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment


@dataclass
class TestCase:
    name: str
    message: str
    expected_arousal: str
    expected_emotion: str
    expected_arousal_ok: bool = True  # arousal inference check
    tolerate_gather: bool = False  # allow one clarifying question


CASES: list[TestCase] = [
    TestCase(
        name="тревога_высокая",
        message="ПАНИКА боюсь умереть на диализе",
        expected_arousal="высокое",
        expected_emotion="страх",
    ),
    TestCase(
        name="тревога_низкая",
        message="немного тревожно перед следующей процедурой",
        expected_arousal="низкое",
        expected_emotion="тревога",
        tolerate_gather=True,
    ),
    TestCase(
        name="злость_высокая",
        message="бешусь просто, всё достало, ненавижу эти процедуры",
        expected_arousal="высокое",
        expected_emotion="злость",
    ),
    TestCase(
        name="злость_средняя",
        message="злюсь на расписание диализа, неудобное время",
        expected_arousal="высокое",  # default — acceptable
        expected_emotion="злость",
        tolerate_gather=True,
    ),
    TestCase(
        name="грусть",
        message="грустно, устал от всего этого, нет сил",
        expected_arousal="низкое",
        expected_emotion="грусть",
    ),
    TestCase(
        name="страх_острый",
        message="боюсь, сердце колотится, не могу успокоиться",
        expected_arousal="высокое",
        expected_emotion="страх",
    ),
]

# Patterns that should NEVER appear in support field
FORBIDDEN_MEDICAL_CLAIMS = (
    "давление под контролем",
    "всё нормально",
    "бояться нечего",
    "опасности нет",
    "ничего страшного с медицинской",
)

TECHNIQUE_ID_PATTERN = re.compile(r'\[p(\d+)\]')


def _check_technique_used(step_now: str) -> str | None:
    """Return technique id if found in step_now, else None."""
    m = TECHNIQUE_ID_PATTERN.search(step_now or "")
    return f"p{m.group(1):0>2}" if m else None


def _check_medical_claim(support: str) -> list[str]:
    lowered = (support or "").lower()
    return [c for c in FORBIDDEN_MEDICAL_CLAIMS if c in lowered]


async def run_test_case(case: TestCase) -> dict:
    from app.llm.langgraph_supervisor.engine import run_first_module
    from app.llm.langgraph_supervisor.models import (
        EmotionalExpertCard,
        FirstModuleInput,
    )
    from app.llm.supervisor.models import CurrentState
    from app.llm.technique_library import infer_arousal, infer_emotions

    # Check arousal inference (no LLM needed)
    detected_arousal = infer_arousal(case.message)
    detected_emotions = sorted(infer_emotions(case.message))
    arousal_ok = detected_arousal == case.expected_arousal

    # Run pipeline (real LLM call)
    # clarification_streak=2 forces delegation so we reliably reach the expert
    state = CurrentState(
        clarification_streak=2,
        goal=f"эмоциональное состояние: {case.expected_emotion}",
        slots={"intake_context": case.message},
    )
    payload = FirstModuleInput(
        user_message=case.message,
        current_state=state,
        message_type="full_message",
        model_tier="max",
        patient_gender="мужской",
    )
    graph_state = await run_first_module(payload)

    reply = graph_state.final_reply or ""
    expert_card = graph_state.expert_card

    technique_id = None
    support_text = ""
    step_now_text = ""
    mode_str = "—"
    medical_violations = []
    has_technique = False
    is_gather = False
    card_strategy = "—"

    if isinstance(expert_card, EmotionalExpertCard):
        support_text = expert_card.support or ""
        step_now_text = expert_card.step_now or ""
        technique_id = _check_technique_used(step_now_text)
        has_technique = technique_id is not None
        is_gather = (expert_card.needs_more_info.value == "да" and
                     (not step_now_text or step_now_text.lower() == "нет"))
        mode_str = "уточнить" if is_gather else "интервенция"
        medical_violations = _check_medical_claim(support_text)
        card_strategy = expert_card.strategy.value if expert_card.strategy else "—"

    # Verdict
    failures = []
    if not arousal_ok:
        failures.append(f"arousal: expected={case.expected_arousal} got={detected_arousal}")
    if not has_technique and not is_gather:
        failures.append("no technique id [pXX] in step_now (and not gather mode)")
    if is_gather and not case.tolerate_gather:
        failures.append("unexpected gather mode (should have proposed technique)")
    if medical_violations:
        failures.append(f"medical claims in support: {medical_violations}")

    return {
        "case": case.name,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "arousal_inferred": detected_arousal,
        "emotions_inferred": detected_emotions,
        "technique_id": technique_id,
        "mode": mode_str,
        "strategy": card_strategy,
        "support": support_text[:80],
        "step_now": step_now_text[:120],
        "reply": reply[:200],
        "execution_kind": graph_state.execution_kind.value if graph_state.execution_kind else "—",
        "graph_path": graph_state.diagnostics.get("graph_path", []),
        "intake_problem": (graph_state.intake_card.problem if graph_state.intake_card else "—"),
        "intake_ready": (graph_state.intake_card.ready_to_delegate.value if graph_state.intake_card else "—"),
        "intake_diag": graph_state.diagnostics.get("intake", {}),
        "expert_diag": graph_state.diagnostics.get("expert", {}),
    }


def _print_result(r: dict) -> None:
    status_icon = "+" if r["status"] == "PASS" else "!"
    print(f"\n{status_icon} [{r['status']}] {r['case']}")
    print(f"  arousal={r['arousal_inferred']}  emotions={r['emotions_inferred']}")
    print(f"  mode={r['mode']}  strategy={r['strategy']}  technique={r['technique_id'] or '—'}")
    print(f"  Поддержка: {r['support']}")
    print(f"  Шаг сейчас: {r['step_now']}")
    print(f"  exec={r.get('execution_kind','—')}  path={r.get('graph_path','')}")
    print(f"  intake_problem={r.get('intake_problem','—')}  ready={r.get('intake_ready','—')}")
    intake_d = r.get("intake_diag", {})
    if intake_d.get("card") is None:
        llm_d = intake_d.get("llm", {})
        failures = llm_d.get("failures", [])
        for f in failures:
            print(f"  intake fail attempt={f.get('attempt')}: {f.get('error_message','?')[:120]}")
            print(f"    raw: {f.get('raw_excerpt','')[:150]}")
    expert_d = r.get("expert_diag", {})
    if expert_d.get("card") is None:
        ex_llm = expert_d.get("llm", {})
        for f in ex_llm.get("failures", []):
            print(f"  expert fail a={f.get('attempt')}: {f.get('error_message','?')[:150]}")
            print(f"    raw: {f.get('raw_excerpt','')[:200]}")
    print(f"  reply: {r['reply']}")
    if r["failures"]:
        for f in r["failures"]:
            print(f"  !! {f}")


async def main() -> None:
    # Force utf-8 output on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_environment()
    print("Phase 3: Technique Library - Live LLM Test")
    print("=" * 60)

    results = []
    for case in CASES:
        print(f"\nRunning: {case.name} …", end="", flush=True)
        try:
            result = await run_test_case(case)
        except Exception as exc:
            result = {
                "case": case.name,
                "status": "ERROR",
                "failures": [str(exc)],
                "arousal_inferred": "—",
                "emotions_inferred": [],
                "technique_id": None,
                "mode": "—",
                "strategy": "—",
                "support": "",
                "step_now": "",
                "reply": "",
            }
        results.append(result)
        print(" done")

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for r in results:
        _print_result(r)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    print(f"\n{'=' * 60}")
    print(f"Total: {len(results)}  PASS: {passed}  FAIL: {failed}  ERROR: {errors}")

    sys.exit(0 if failed == 0 and errors == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
