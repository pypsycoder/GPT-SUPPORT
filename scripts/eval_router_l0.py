"""
Замер L0 против текущего keyword-роутера на размеченном наборе.

Метрики в порядке важности:
  1. recall по safety — пропуск дороже всего остального вместе взятого;
  2. ложные срабатывания safety — каждое стоит пациенту неуместного
     кризисного шаблона;
  3. доля запросов, обслуженных без вызова модели;
  4. точность там, где L0 вообще берётся отвечать.

Набор делает scripts/label_intents.py. Вызовов модели не требует.

Запуск:
    python scripts/eval_router_l0.py [--labels путь.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment

load_environment()

from app.llm import router_l0  # noqa: E402
from app.llm.router import classify_request  # noqa: E402

DEFAULT_LABELS = ROOT_DIR / "LLM_test" / "cases" / "intent_labels.json"


def evaluate(rows: list[dict]) -> dict:
    stats = {
        "total": len(rows),
        "l0_resolved": 0,
        "l0_correct": 0,
        "l0_wrong": [],
        "safety_truth": 0,
        "old_safety_hit": 0,
        "old_safety_false": [],
        "l0_safety_hit": 0,
        "l0_safety_false": [],
        "l0_concern": 0,
    }

    for row in rows:
        truth = row["intent"]
        text = row["text"]
        decision = router_l0.classify(text)
        old = classify_request(text, "text").request_type.value

        if truth == "safety":
            stats["safety_truth"] += 1
            if old == "safety":
                stats["old_safety_hit"] += 1
            if decision.safety_level == "urgent":
                stats["l0_safety_hit"] += 1
        else:
            if old == "safety":
                stats["old_safety_false"].append(text)
            if decision.safety_level == "urgent":
                stats["l0_safety_false"].append(text)

        if decision.safety_level == "concern":
            stats["l0_concern"] += 1

        if decision.resolved:
            stats["l0_resolved"] += 1
            # continuation сравнивать не с чем: разметка шла без контекста.
            if decision.intent == "continuation":
                continue
            if decision.intent == truth:
                stats["l0_correct"] += 1
            else:
                stats["l0_wrong"].append(
                    {"text": text, "truth": truth, "l0": decision.intent, "rule": decision.rule}
                )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    args = parser.parse_args()

    rows = json.loads(args.labels.read_text(encoding="utf-8"))["labels"]
    stats = evaluate(rows)

    print(f"размеченных сообщений: {stats['total']}")
    print(f"\n=== SAFETY (истинных: {stats['safety_truth']}) ===")
    print(f"  поймал старый роутер: {stats['old_safety_hit']}/{stats['safety_truth']}")
    print(f"  поймал L0:            {stats['l0_safety_hit']}/{stats['safety_truth']}")
    print(f"  ложных у старого:     {len(stats['old_safety_false'])}")
    for text in stats["old_safety_false"]:
        print(f"     - {text[:70]!r}")
    print(f"  ложных у L0:          {len(stats['l0_safety_false'])}")
    for text in stats["l0_safety_false"]:
        print(f"     - {text[:70]!r}")
    print(f"  поднято до concern:   {stats['l0_concern']}")

    resolved = stats["l0_resolved"]
    judged = resolved - sum(
        1 for r in rows if router_l0.classify(r["text"]).intent == "continuation"
    )
    print(f"\n=== ПОКРЫТИЕ ===")
    print(f"  L0 ответил уверенно:  {resolved}/{stats['total']} ({resolved / stats['total']:.0%})")
    if judged:
        print(f"  из них верно:         {stats['l0_correct']}/{judged} ({stats['l0_correct'] / judged:.0%})")
    print(f"  ошибки L0: {len(stats['l0_wrong'])}")
    for item in stats["l0_wrong"]:
        print(f"     - {item['text'][:55]!r} истина={item['truth']} L0={item['l0']} ({item['rule']})")

    by_intent = Counter(r["intent"] for r in rows)
    print(f"\nраспределение истины: {dict(by_intent.most_common())}")


if __name__ == "__main__":
    main()
