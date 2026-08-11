"""
Кризисные метрики: старый keyword-роутер против L0.

Мерит на наборе из scripts/gen_safety_set.py. Вызовов модели не требует.

Что считаем, в порядке важности:
  1. recall по urgent — пропуск дороже всего остального вместе взятого;
  2. precision по urgent — каждое ложное срабатывание подменяет ответ человеку
     кризисным протоколом;
  3. отдельно: сколько concern ошибочно поднято до urgent. Это худший вид
     ложного срабатывания — человеку просто тяжело, а он получает телефон доверия;
  4. разбивка промахов по классам и правилам.

Про train/holdout: паттерны правятся, глядя только на train. Holdout открывается
один раз в конце. Без этого регулярки неизбежно подгоняются под собственный тест.

Запуск:
    python scripts/eval_safety.py [--split holdout] [--show-misses]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment

load_environment()

from app.llm import router_l0  # noqa: E402
from app.llm.router import RequestType, classify_request  # noqa: E402

DEFAULT_SET = ROOT_DIR / "LLM_test" / "cases" / "safety_set.json"

# Классы, на которых детектор обязан сработать как urgent.
URGENT_CLASSES = {"urgent_psych", "urgent_medical"}


def _old_router_urgent(text: str) -> bool:
    return classify_request(text, "text").request_type is RequestType.SAFETY


def _l0_urgent(text: str) -> bool:
    return router_l0.classify(text).safety_level == "urgent"


def _prf(hits: int, misses: int, false_alarms: int) -> tuple[float, float]:
    recall = hits / (hits + misses) if (hits + misses) else 0.0
    precision = hits / (hits + false_alarms) if (hits + false_alarms) else 0.0
    return recall, precision


def evaluate(items: list[dict], detector) -> dict:
    hits = misses = false_alarms = 0
    concern_escalated = 0
    miss_rows: list[dict] = []
    false_rows: list[dict] = []
    by_class: dict[str, Counter] = defaultdict(Counter)

    for item in items:
        klass = item["intended"]
        fired = detector(item["text"])
        should_fire = klass in URGENT_CLASSES

        by_class[klass]["total"] += 1
        if fired:
            by_class[klass]["fired"] += 1

        if should_fire and fired:
            hits += 1
        elif should_fire and not fired:
            misses += 1
            miss_rows.append(item)
        elif not should_fire and fired:
            false_alarms += 1
            false_rows.append(item)
            if klass == "concern":
                concern_escalated += 1

    recall, precision = _prf(hits, misses, false_alarms)
    return {
        "hits": hits,
        "misses": misses,
        "false_alarms": false_alarms,
        "concern_escalated": concern_escalated,
        "recall": recall,
        "precision": precision,
        "miss_rows": miss_rows,
        "false_rows": false_rows,
        "by_class": {k: dict(v) for k, v in by_class.items()},
    }


def _print_block(name: str, stats: dict, total_urgent: int) -> None:
    print(f"\n--- {name} ---")
    print(f"  recall    {stats['recall']:.0%}  ({stats['hits']}/{total_urgent})")
    print(f"  precision {stats['precision']:.0%}  (ложных: {stats['false_alarms']})")
    print(f"  concern поднято до urgent: {stats['concern_escalated']}")
    fired = {k: f"{v.get('fired', 0)}/{v['total']}" for k, v in sorted(stats["by_class"].items())}
    print(f"  срабатываний по классам: {fired}")


def main() -> None:
    # Windows-консоль по умолчанию cp1251 и падает на «→», «—» и кавычках.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", type=Path, default=DEFAULT_SET)
    parser.add_argument("--split", choices=["train", "holdout", "all"], default="train")
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.set.read_text(encoding="utf-8"))
    items = payload["items"]
    if args.split != "all":
        items = [i for i in items if i.get("split") == args.split]

    total_urgent = sum(1 for i in items if i["intended"] in URGENT_CLASSES)
    print(f"выборка: {args.split} | всего {len(items)} | urgent-классов {total_urgent}")
    print(f"состав: {dict(Counter(i['intended'] for i in items).most_common())}")

    old = evaluate(items, _old_router_urgent)
    new = evaluate(items, _l0_urgent)

    _print_block("старый keyword-роутер", old, total_urgent)
    _print_block("L0", new, total_urgent)

    print("\n=== сводка ===")
    print(f"{'':26s}{'старый':>10s}{'L0':>10s}")
    for label, key, fmt in (
        ("recall", "recall", "pct"),
        ("precision", "precision", "pct"),
        ("пропусков", "misses", "int"),
        ("ложных срабатываний", "false_alarms", "int"),
        ("concern -> urgent", "concern_escalated", "int"),
    ):
        a, b = old[key], new[key]
        if fmt == "pct":
            print(f"{label:26s}{a:>9.0%}{b:>10.0%}")
        else:
            print(f"{label:26s}{a:>10d}{b:>10d}")

    if args.show_misses:
        print("\n=== промахи L0 (что чинить) ===")
        for row in new["miss_rows"]:
            print(f"  [{row['intended']}] {row['text'][:80]!r}")
        print("\n=== ложные срабатывания L0 ===")
        for row in new["false_rows"]:
            decision = router_l0.classify(row["text"])
            print(f"  [{row['intended']}] {row['text'][:70]!r} правило={decision.rule}")


if __name__ == "__main__":
    main()
