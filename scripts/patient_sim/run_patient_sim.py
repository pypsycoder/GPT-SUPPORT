"""Ролевая имитация пациента против реального LLM-ассистента.

Прогоняет библиотеку персон (``personas.py``) и сценариев (``scenarios.py``)
через тот же вход, что использует продовый чат (``pipeline_adapter.py`` —
``classify_request_async`` → ``LLMPipeline.process()``), несколько ходов на
сценарий, несколько перефразировок одного смысла на ход, оценивает каждый
ответ (``evaluators.py``) и пишет читаемый markdown-отчёт (``report.py``).

Полностью неинтерактивен — ни одного ``input()``, безопасно дёргать из
планировщика. Ничего не пишет в реальную БД (``db=None`` в адаптере).

Запуск:
    python -m scripts.patient_sim.run_patient_sim
    python -m scripts.patient_sim.run_patient_sim --quick
    python -m scripts.patient_sim.run_patient_sim --personas p01,p03 --no-judge
    python -m scripts.patient_sim.run_patient_sim --output my_report.md

Для ночного автозапуска планировщику нужна ровно эта команда (без --quick,
без флагов) — она использует те флаги LLM_ROUTER_L0/L1/L2/LLM_AGENT_TOOLS,
что заданы в .env на момент запуска, и пишет файл в
test-results/patient-sim/<дата>.md.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment  # noqa: E402

load_environment()

from scripts.patient_sim.evaluators import evaluate_scenario, evaluate_turn  # noqa: E402
from scripts.patient_sim.patient_agent import PatientAgent, describe_mode  # noqa: E402
from scripts.patient_sim.personas import PERSONAS, Persona  # noqa: E402
from scripts.patient_sim.pipeline_adapter import PatientSession  # noqa: E402
from scripts.patient_sim.report import IterationRun, TurnRecord, render_report  # noqa: E402
from scripts.patient_sim.scenarios import Scenario, scenarios_for  # noqa: E402

logger = logging.getLogger("patient_sim")

_FLAG_NAMES = (
    "LLM_SINGLE_AGENT",
    "LLM_ROUTER_L0",
    "LLM_ROUTER_L1",
    "LLM_ROUTER_L2",
    "LLM_AGENT_TOOLS",
)

_DEFAULT_OUTPUT_DIR = ROOT_DIR / "test-results" / "patient-sim"


def _flags_summary() -> str:
    parts = []
    for name in _FLAG_NAMES:
        value = str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}
        parts.append(f"{name}={'on' if value else 'off'}")
    return ", ".join(parts)


def _judge_mode(run_judge: bool) -> str:
    if not run_judge:
        return "выключен (--no-judge)"
    return "включён (app.llm.agent.judge, GigaChat-Max)"


async def _run_iteration(
    *,
    scenario: Scenario,
    persona: Persona,
    iteration: int,
    patient_agent: PatientAgent,
    used_variants_by_turn: dict[int, list[str]],
    run_judge: bool,
) -> IterationRun:
    session = PatientSession(
        patient_gender=persona.gender,
        thread_id=f"sim-{scenario.id}-iter{iteration}",
    )
    transcript: list[dict] = []
    turn_records: list[TurnRecord] = []
    turn_signals = []

    for turn_index, turn in enumerate(scenario.turns):
        used_variants = used_variants_by_turn.setdefault(turn_index, [])
        text, source = await patient_agent.turn_text(
            turn=turn,
            turn_index=turn_index,
            iteration=iteration,
            total_iterations=scenario.iterations,
            transcript=transcript,
            used_variants=used_variants,
        )
        used_variants.append(text)
        transcript.append({"role": "patient", "content": text})

        started = time.monotonic()
        result = await session.send(text)
        latency_ms = int((time.monotonic() - started) * 1000)

        response_text = result.response.response
        transcript.append({"role": "bot", "content": response_text})

        signals = await evaluate_turn(
            user_input=text,
            response_text=response_text,
            diagnostics=result.response.diagnostics or {},
            run_judge=run_judge,
        )
        turn_signals.append(signals)
        turn_records.append(
            TurnRecord(
                index=turn_index,
                user_input=text,
                source=source,
                response_text=response_text,
                signals=signals,
                latency_ms=latency_ms,
            )
        )

    verdict = evaluate_scenario(
        expect_crisis=scenario.expect_crisis,
        forbid_personalized_advice=scenario.forbid_personalized_advice,
        turn_signals=turn_signals,
    )
    return IterationRun(
        scenario=scenario, persona=persona, iteration=iteration, turns=turn_records, verdict=verdict
    )


async def _run_all(*, scenarios: list[Scenario], quick: bool, run_judge: bool) -> list[IterationRun]:
    runs: list[IterationRun] = []

    for scenario in scenarios:
        persona = PERSONAS[scenario.persona_id]
        patient_agent = PatientAgent(persona)
        iterations = 1 if quick else scenario.iterations
        used_variants_by_turn: dict[int, list[str]] = {}

        logger.info(
            "[patient_sim] сценарий %s (%s) — %d итерация(й), режим пациента=%s",
            scenario.id, scenario.title, iterations, patient_agent.mode,
        )

        for iteration in range(iterations):
            try:
                run = await _run_iteration(
                    scenario=scenario,
                    persona=persona,
                    iteration=iteration,
                    patient_agent=patient_agent,
                    used_variants_by_turn=used_variants_by_turn,
                    run_judge=run_judge,
                )
            except Exception as exc:  # noqa: BLE001 — один сбой не должен рушить ночной прогон
                logger.exception(
                    "[patient_sim] сценарий %s итерация %d упал: %s", scenario.id, iteration, exc
                )
                from scripts.patient_sim.evaluators import ScenarioVerdict

                run = IterationRun(
                    scenario=scenario,
                    persona=persona,
                    iteration=iteration,
                    turns=[],
                    verdict=ScenarioVerdict(
                        verdict="FAIL", reasons=[f"Сценарий упал с исключением: {exc.__class__.__name__}: {exc}"]
                    ),
                )
            runs.append(run)
            logger.info(
                "[patient_sim]   итерация %d/%d → %s",
                iteration + 1, iterations, run.verdict.verdict,
            )

    return runs


def _print_console_summary(runs: list[IterationRun], report_path: Path) -> None:
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for r in runs:
        counts[r.verdict.verdict] += 1
    print(f"\npatient-sim: {len(runs)} перефразировок — {counts['PASS']} PASS, {counts['WARN']} WARN, {counts['FAIL']} FAIL")
    fails = [r for r in runs if r.verdict.verdict == "FAIL"]
    if fails:
        print("FAIL:")
        for r in fails:
            reason = r.verdict.reasons[0] if r.verdict.reasons else "(без деталей)"
            print(f"  - {r.scenario.id} итерация {r.iteration + 1}: {reason}")
    print(f"Отчёт: {report_path}")


def main() -> None:
    # Windows-консоль по умолчанию в cp1251/cp866 — кириллица в логах иначе
    # превращается в «?????». Файл отчёта пишется через Path.write_text(utf-8)
    # отдельно и от этого не зависит.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=None, help="Путь к отчёту (по умолчанию test-results/patient-sim/<дата>.md)")
    parser.add_argument("--personas", type=str, default=None, help="Список id персон через запятую, например p01,p03")
    parser.add_argument("--quick", action="store_true", help="Одна перефразировка на сценарий вместо полного набора — для быстрой проверки после правки")
    parser.add_argument("--no-judge", action="store_true", help="Не звать LLM-судью (быстрее, без оценки тона/советов)")
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG-логирование в stderr")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    persona_ids = [p.strip() for p in args.personas.split(",")] if args.personas else None
    scenarios = scenarios_for(persona_ids)
    if not scenarios:
        print(f"Нет сценариев для персон: {args.personas}", file=sys.stderr)
        sys.exit(1)

    run_judge = not args.no_judge
    started_at = datetime.now()
    t0 = time.monotonic()

    runs = asyncio.run(_run_all(scenarios=scenarios, quick=args.quick, run_judge=run_judge))

    duration_s = time.monotonic() - t0
    turn_count = sum(len(r.turns) for r in runs)

    run_meta = {
        "date": date.today().isoformat(),
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": duration_s,
        "flags_summary": _flags_summary(),
        "patient_agent_mode": describe_mode(),
        "judge_mode": _judge_mode(run_judge),
        "scenario_count": len(scenarios),
        "turn_count": turn_count,
        "scenarios": scenarios,
        "personas": PERSONAS,
    }
    report_md = render_report(run_meta=run_meta, runs=runs)

    output_path = args.output or (_DEFAULT_OUTPUT_DIR / f"{date.today().isoformat()}.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_md, encoding="utf-8")

    _print_console_summary(runs, output_path)

    if any(r.verdict.verdict == "FAIL" for r in runs):
        sys.exit(1)


if __name__ == "__main__":
    main()
