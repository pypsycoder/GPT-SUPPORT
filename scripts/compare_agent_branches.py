"""
Сравнение старой цепочки узлов и одноагентной ветки (шаг 4).

Гоняет один и тот же набор кейсов через обе ветки и сравнивает:
  * совпадение интента и safety-флага;
  * оценку офлайн-судьи (GigaChat-2-Max): relevance/safety/tone/actionability + violations;
  * токены и латентность.

Ветка переключается переменной окружения внутри процесса, поэтому обе меряются
в одинаковых условиях: тот же пациент, тот же контекст, тот же набор реплик.
Каждый кейс идёт в своём треде — истории друг друга они не видят.

Запуск:
    python scripts/compare_agent_branches.py [--patient-id 1] [--no-judge]

Ничего не коммитит: LLMRequestLog откатывается, chat_messages не пишутся.
Единственная запись — llm.llm_call_log телеметрией, треды помечены 'cmp-'.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path
from statistics import mean

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment

load_environment()

from app.llm import agent  # noqa: E402
from app.llm.agent.judge import judge_reply  # noqa: E402
from app.llm.pipeline import LLMPipeline, LLMRequest  # noqa: E402
from app.llm.router import classify_request  # noqa: E402
from core.db.session import async_session_factory  # noqa: E402

DEFAULT_CASES = ROOT_DIR / "LLM_test" / "cases" / "chat_quality_cases.yaml"
REPORTS_DIR = ROOT_DIR / "LLM_test" / "reports"

BRANCHES = ("legacy", "single_agent")


def load_cases(path: Path) -> list[dict]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    return list(payload.get("cases") or [])


def _supervisor(diagnostics: dict) -> dict:
    return diagnostics.get("supervisor") or {}


def _intent_of(diagnostics: dict) -> str:
    """Единый словарь интента для обеих веток."""
    sup = _supervisor(diagnostics)
    if sup.get("branch") == "single_agent":
        return str((sup.get("agent") or {}).get("intent") or "unknown")
    agents = [str(a) for a in (sup.get("selected_agents") or [])]
    if agents:
        return agents[0]
    # Старая ветка на уточнении и завершении экспертов не выбирает.
    return {"уточнение": "clarify", "завершение": "smalltalk"}.get(
        str(sup.get("execution_kind") or ""), "unknown"
    )


def _safety_of(diagnostics: dict) -> str:
    sup = _supervisor(diagnostics)
    if sup.get("branch") == "single_agent":
        return str((sup.get("agent") or {}).get("safety_level") or "unknown")
    # У старой ветки собственного safety-поля нет: кризис ловит BoundaryGuardStage
    # до supervisor, поэтому дошедший сюда ход считаем 'none'.
    guard = diagnostics.get("boundary_guard") or {}
    return "urgent" if guard.get("type") == "crisis_signal" else "none"


def _llm_calls(diagnostics: dict) -> int:
    sup = _supervisor(diagnostics)
    if sup.get("branch") == "single_agent":
        return int((sup.get("agent") or {}).get("llm_calls") or 0)
    total = 0
    for node in ("intake", "delegation", "expert"):
        llm = (sup.get(node) or {}).get("llm") or {}
        total += int(llm.get("attempts_total") or 0) + int(llm.get("repair_attempts") or 0)
    return total


async def run_branch(branch: str, cases: list[dict], patient_id: int) -> list[dict]:
    os.environ[agent.ENV_FLAG] = "1" if branch == "single_agent" else "0"
    pipeline = LLMPipeline()
    stamp = int(time.time())
    rows: list[dict] = []

    async with async_session_factory() as session:
        try:
            for case in cases:
                case_id = str(case.get("id") or "?")
                text = str(case.get("text") or "")
                router_result = classify_request(text, "text")
                started = time.monotonic()
                try:
                    response = await pipeline.process(
                        LLMRequest(
                            patient_id=patient_id,
                            user_input=text,
                            source="text",
                            router_result=router_result,
                            supervisor_state=None,
                            db=session,
                            thread_id=f"cmp-{branch}-{case_id}-{stamp}",
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    rows.append({"case_id": case_id, "text": text, "error": f"{type(exc).__name__}: {exc}"})
                    print(f"  {case_id}: ОШИБКА {type(exc).__name__}: {exc}")
                    continue

                diagnostics = response.diagnostics or {}
                rows.append(
                    {
                        "case_id": case_id,
                        "category": case.get("category"),
                        "expected_intent": case.get("expected_intent"),
                        "text": text,
                        "reply": response.response,
                        "intent": _intent_of(diagnostics),
                        "safety": _safety_of(diagnostics),
                        "llm_calls": _llm_calls(diagnostics),
                        "tokens_in": response.tokens_input,
                        "tokens_out": response.tokens_output,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                        "tier": response.actual_model_tier,
                        "fallback": bool(_supervisor(diagnostics).get("error")),
                    }
                )
                print(f"  {case_id}: intent={rows[-1]['intent']} calls={rows[-1]['llm_calls']} "
                      f"tok={response.tokens_input}+{response.tokens_output}")
        finally:
            await session.rollback()

    os.environ.pop(agent.ENV_FLAG, None)
    return rows


async def add_judge_scores(rows: list[dict]) -> None:
    for row in rows:
        if row.get("error"):
            continue
        verdict = await judge_reply(user_message=row["text"], bot_reply=row["reply"])
        if verdict is None:
            row["judge"] = None
            continue
        row["judge"] = {
            "relevance": int(verdict.relevance),
            "safety": int(verdict.safety),
            "tone": int(verdict.tone),
            "actionability": int(verdict.actionability),
            "total": verdict.total,
            "violations": list(verdict.violations),
            "comment": verdict.comment,
        }


def _avg(values: list[float]) -> float:
    return round(mean(values), 2) if values else 0.0


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r.get("error")]
    judged = [r for r in ok if r.get("judge")]
    return {
        "cases": len(rows),
        "ok": len(ok),
        "errors": len(rows) - len(ok),
        "fallbacks": sum(1 for r in ok if r.get("fallback")),
        "avg_llm_calls": _avg([r["llm_calls"] for r in ok]),
        "avg_tokens_in": _avg([r["tokens_in"] for r in ok]),
        "avg_tokens_out": _avg([r["tokens_out"] for r in ok]),
        "avg_latency_ms": _avg([r["latency_ms"] for r in ok]),
        "judge_relevance": _avg([r["judge"]["relevance"] for r in judged]),
        "judge_safety": _avg([r["judge"]["safety"] for r in judged]),
        "judge_tone": _avg([r["judge"]["tone"] for r in judged]),
        "judge_actionability": _avg([r["judge"]["actionability"] for r in judged]),
        "judge_total": _avg([r["judge"]["total"] for r in judged]),
        "violations": sum(len(r["judge"]["violations"]) for r in judged),
    }


def render_table(summaries: dict[str, dict], agreement: dict) -> str:
    legacy, single = summaries["legacy"], summaries["single_agent"]
    rows = [
        ("Кейсов ok / всего", f"{legacy['ok']}/{legacy['cases']}", f"{single['ok']}/{single['cases']}"),
        ("Откатов на старую ветку", "—", str(single["fallbacks"])),
        ("Вызовов LLM на кейс", legacy["avg_llm_calls"], single["avg_llm_calls"]),
        ("Токенов вход", legacy["avg_tokens_in"], single["avg_tokens_in"]),
        ("Токенов выход", legacy["avg_tokens_out"], single["avg_tokens_out"]),
        ("Латентность, мс", legacy["avg_latency_ms"], single["avg_latency_ms"]),
        ("Судья: relevance", legacy["judge_relevance"], single["judge_relevance"]),
        ("Судья: safety", legacy["judge_safety"], single["judge_safety"]),
        ("Судья: tone", legacy["judge_tone"], single["judge_tone"]),
        ("Судья: actionability", legacy["judge_actionability"], single["judge_actionability"]),
        ("Судья: сумма из 20", legacy["judge_total"], single["judge_total"]),
        ("Нарушений всего", legacy["violations"], single["violations"]),
    ]
    width = max(len(r[0]) for r in rows) + 2
    lines = [f"{'Метрика':<{width}} {'старая':>12} {'агент':>12}", "-" * (width + 26)]
    lines += [f"{name:<{width}} {str(a):>12} {str(b):>12}" for name, a, b in rows]
    lines.append("")
    lines.append(f"Совпадение интента:  {agreement['intent']}")
    lines.append(f"Совпадение safety:   {agreement['safety']}")
    return "\n".join(lines)


def compute_accuracy(rows: list[dict]) -> dict:
    """Попадание в ожидаемый интент — если он в кейсе указан.

    Согласие веток само по себе ничего не говорит: они могут дружно ошибаться.
    Отдельно считаем по категориям, потому что средняя цифра скрывает главное —
    на каких именно классах ветка систематически промахивается.
    """
    judged = [r for r in rows if not r.get("error") and r.get("expected_intent")]
    if not judged:
        return {"total": 0}

    hits = sum(1 for r in judged if r["intent"] == r["expected_intent"])
    by_category: dict[str, dict[str, int]] = {}
    for row in judged:
        bucket = by_category.setdefault(row.get("category") or "?", {"hit": 0, "total": 0})
        bucket["total"] += 1
        if row["intent"] == row["expected_intent"]:
            bucket["hit"] += 1

    return {
        "total": len(judged),
        "hits": hits,
        "accuracy": hits / len(judged),
        "by_category": by_category,
        "misses": [
            {"case_id": r["case_id"], "expected": r["expected_intent"], "got": r["intent"]}
            for r in judged
            if r["intent"] != r["expected_intent"]
        ],
    }


def compute_agreement(legacy: list[dict], single: list[dict]) -> dict:
    by_id = {r["case_id"]: r for r in single if not r.get("error")}
    pairs = [(r, by_id[r["case_id"]]) for r in legacy if not r.get("error") and r["case_id"] in by_id]
    if not pairs:
        return {"intent": "нет пар", "safety": "нет пар", "mismatches": []}
    intent_hits = sum(1 for a, b in pairs if a["intent"] == b["intent"])
    safety_hits = sum(1 for a, b in pairs if a["safety"] == b["safety"])
    return {
        "intent": f"{intent_hits}/{len(pairs)} ({intent_hits / len(pairs):.0%})",
        "safety": f"{safety_hits}/{len(pairs)} ({safety_hits / len(pairs):.0%})",
        "mismatches": [
            {"case_id": a["case_id"], "legacy": a["intent"], "agent": b["intent"]}
            for a, b in pairs
            if a["intent"] != b["intent"]
        ],
    }


async def main() -> None:
    # Windows-консоль в cp1251 роняет вывод на кириллице и стрелках.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--patient-id", type=int, default=1)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--no-judge", action="store_true")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    print(f"кейсов: {len(cases)}")

    results: dict[str, list[dict]] = {}
    for branch in BRANCHES:
        print(f"\n=== ветка {branch} ===")
        results[branch] = await run_branch(branch, cases, args.patient_id)
        if not args.no_judge:
            print("  судья...")
            await add_judge_scores(results[branch])

    summaries = {b: summarize(results[b]) for b in BRANCHES}
    agreement = compute_agreement(results["legacy"], results["single_agent"])
    accuracy = {b: compute_accuracy(results[b]) for b in BRANCHES}
    table = render_table(summaries, agreement)
    print("\n" + table)

    if accuracy["legacy"].get("total"):
        print("\n=== попадание в ожидаемый интент ===")
        for branch in BRANCHES:
            stats = accuracy[branch]
            print(f"  {branch:14s} {stats['hits']}/{stats['total']} ({stats['accuracy']:.0%})")
        print("\n  по категориям:")
        print(f"    {'категория':16s}{'старая':>10s}{'агент':>10s}")
        for name in sorted(accuracy["legacy"]["by_category"]):
            a = accuracy["legacy"]["by_category"][name]
            b = accuracy["single_agent"]["by_category"].get(name, {"hit": 0, "total": 0})
            legacy_cell = "{}/{}".format(a["hit"], a["total"])
            agent_cell = "{}/{}".format(b["hit"], b["total"])
            print(f"    {name:16s}{legacy_cell:>10s}{agent_cell:>10s}")
        for branch in BRANCHES:
            misses = accuracy[branch]["misses"]
            if misses:
                print(f"\n  промахи {branch}:")
                for m in misses:
                    print(f"    {m['case_id']:28s} ждали {m['expected']:18s} получили {m['got']}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"agent_branch_compare_{time.strftime('%Y.%m.%d_%H.%M')}.json"
    out.write_text(
        json.dumps(
            {"summaries": summaries, "agreement": agreement, "accuracy": accuracy, "results": results},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nотчёт: {out}")


if __name__ == "__main__":
    asyncio.run(main())
