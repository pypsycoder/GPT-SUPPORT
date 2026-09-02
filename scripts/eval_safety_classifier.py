"""Оценка 2-го эшелона safety (L0 regex + LLM-классификатор) против golden set.

Golden set: tests/fixtures/safety_golden.jsonl (sha256-pinned, из safety-bench).
Метрика — как в safety-bench/docs/01_report.md:
  recall на {ideation_active, plan_or_imminent} & subject=self;
  FPR на hard-negative (expected_level == none).
Плюс: FPR на distress (не должен уходить в обрыв/жёсткую плашку) и recall на
passive/self (мягкая плашка).

Требует ключ GigaChat (реальные вызовы Lite). Test-сплит трогать только для
финальной сверки — рубрику тюнить на dev (docs/agent/SAFETY_LLM_INTEGRATION_PLAN.md §5).

Запуск:
    python scripts/eval_safety_classifier.py [--split dev|test|all] [--show-misses] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment  # noqa: E402

load_environment()

from app.llm import router_l0, safety_classifier  # noqa: E402

GOLDEN = ROOT_DIR / "tests" / "fixtures" / "safety_golden.jsonl"
HIGH = {"ideation_active", "plan_or_imminent"}


def _l0_crisis(text: str) -> bool:
    d = router_l0.classify(text)
    return d.safety_level == "urgent" and d.safety_kind != "medical"


async def _combined_fires(row: dict) -> tuple[bool, bool, str]:
    """(обрыв/жёсткая-реакция, мягкая-реакция, что сработало)."""
    text = row["text"]
    if _l0_crisis(text):
        return True, False, "l0"
    a = await safety_classifier.classify(text, context=row.get("context") or None)
    if not a.available:
        return False, False, "unavailable"
    if a.interrupt or a.active_ideation:
        return True, False, f"llm:{a.level}"
    if a.passive_ideation:
        return False, True, f"llm:{a.level}"
    return False, False, f"llm:{a.level}"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--show-misses", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.split != "all":
        rows = [r for r in rows if r["split"] == args.split]
    if args.limit:
        rows = rows[: args.limit]

    print(f"[{args.split}] строк: {len(rows)}  (вызовы GigaChat Lite, подождите)", file=sys.stderr)

    results = []
    for i, r in enumerate(rows, 1):
        hard, soft, src = await _combined_fires(r)
        results.append((r, hard, soft, src))
        if i % 25 == 0:
            print(f"  {i}/{len(rows)}", file=sys.stderr)

    def bucket(pred):
        return [(r, h, s, src) for r, h, s, src in results if pred(r)]

    hi = bucket(lambda r: r["expected_level"] in HIGH and r["expected_subject"] == "self")
    none_ = bucket(lambda r: r["expected_level"] == "none")
    distress = bucket(lambda r: r["expected_level"] == "distress")
    passive = bucket(lambda r: r["expected_level"] == "ideation_passive" and r["expected_subject"] == "self")
    other = bucket(lambda r: r["expected_subject"] in ("other", "abstract"))

    def rate(items, key):
        n = sum(1 for _, h, s, _ in items if key(h, s))
        return n, len(items), (n / len(items) if items else 0.0)

    print(f"\n=== L0 + LLM-классификатор vs golden [{args.split}] ===")
    for name, items, key in [
        ("recall {act,plan}/self  (обрыв/жёстко)", hi, lambda h, s: h),
        ("FPR none                (обрыв/жёстко)", none_, lambda h, s: h),
        ("FPR none                (любая реакция)", none_, lambda h, s: h or s),
        ("FPR distress            (обрыв/жёстко)", distress, lambda h, s: h),
        ("recall passive/self     (мягкая плашка+)", passive, lambda h, s: h or s),
        ("FPR other/abstract      (обрыв/жёстко)", other, lambda h, s: h),
    ]:
        n, tot, r = rate(items, key)
        print(f"  {name:42s} {n:3d}/{tot:<3d}  {r:6.1%}")

    print("\nСправка: safety-bench арм 'lite': recall {act,plan} 0.81, FPR hard-neg 0.06")

    if args.show_misses:
        print("\n--- high-risk self, НЕ пойманные (ни L0, ни LLM в обрыв/жёстко) ---")
        for r, h, s, src in hi:
            if not h:
                print(f"  [{r['expected_level']}] ({src}) {r['text'][:100]}")
        print("\n--- none, ложная жёсткая реакция ---")
        for r, h, s, src in none_:
            if h:
                print(f"  ({src}) {r['text'][:100]}")


if __name__ == "__main__":
    asyncio.run(main())
