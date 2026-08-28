"""
Замер каскада L0/L1/L2 против старого keyword-роутера на размеченном наборе.

По образцу scripts/eval_router_l0.py, но на уровне итогового RouterResult
(request_type), а не только L0. Метрики в порядке важности:

  1. safety recall/false positives — как в eval_router_l0.py;
  2. точность request_type там, где старый роутер и каскад расходятся;
  3. доля сообщений, дошедших до L2 (цель < 15%, часть 9.2 манула) — требует
     живых учётных данных GigaChat (эмбеддинги + Lite), без них L1/L2
     возвращают "не уверен" и всё падает в откат на старый роутер.

Запуск (нужен реальный доступ к GigaChat — эмбеддинги для L1 и Lite для L2):
    python scripts/eval_router_cascade.py [--labels путь.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment

load_environment()

from app.llm.router import classify_request  # noqa: E402
from app.llm.router_cascade import classify_request_async  # noqa: E402

# stats["l1_hits"]/["l2_hits"]/["fallback_hits"] были объявлены, но никогда не
# заполнялись — метрика №3 из докстринга ("доля сообщений, дошедших до L2")
# фактически не считалась и не печаталась. classify_request_async() не
# возвращает resolved_by наружу (RouterResult этого не хранит), поэтому
# ловим его тем же способом, что и логи прода — через DEBUG-строку
# "[router_cascade] resolved_by=%s", которую сама функция уже пишет.
_RESOLVED_BY_RE = re.compile(r"resolved_by=(\w+)")


class _ResolvedByCounter(logging.Handler):
    def __init__(self, stats: dict) -> None:
        super().__init__(level=logging.DEBUG)
        self.stats = stats

    def emit(self, record: logging.LogRecord) -> None:
        match = _RESOLVED_BY_RE.search(record.getMessage())
        if match:
            self.stats[f"{match.group(1)}_hits"] += 1

DEFAULT_LABELS = ROOT_DIR / "LLM_test" / "cases" / "intent_labels.json"

# ВАЖНО: поле router_request_type в разметке не годится в качестве truth —
# оно совпадает со старым classify_request буквально построчно (проверено:
# 104/104), то есть похоже на записанный снимок вывода старого роутера на
# момент разметки, а не независимую оценку человека. У него те же баги:
# "давление 200 на 100" размечено как router_request_type=safety, хотя
# intent (с обоснованием-rationale) для той же строки — data_entry.
# Поэтому truth строим сами из intent, у которого есть rationale и который
# размечался как раз для критики роутера (см. app/llm/pipeline/STRUCTURE.md,
# «Роутер» — почему старый keyword-роутер требовал замены).
_INTENT_TO_REQUEST_TYPE = {
    "smalltalk": "simple",
    "data_entry": "clinical",
    "emotional_support": "emotional",
    "education": "clinical",  # старая система уже так классифицирует, не меняю конвенцию
    "other": "simple",
    "safety": "safety",
}


async def evaluate(rows: list[dict]) -> dict:
    stats = {
        "total": len(rows),
        "safety_truth": 0,
        "old_safety_hit": 0,
        "old_safety_false": [],
        "cascade_safety_hit": 0,
        "cascade_safety_false": [],
        "old_correct": 0,
        "cascade_correct": 0,
        "judged": 0,
        "l1_hits": 0,
        "l2_hits": 0,
        "fallback_hits": 0,
        "l0_early_or_error": 0,
        "disagreements": [],
    }

    cascade_logger = logging.getLogger("gpt-support-llm.router_cascade")
    prev_level = cascade_logger.level
    cascade_logger.setLevel(logging.DEBUG)
    counter = _ResolvedByCounter(stats)
    cascade_logger.addHandler(counter)

    for row in rows:
        text = row["text"]
        truth = _INTENT_TO_REQUEST_TYPE.get(row.get("intent"))

        old = classify_request(text, "text").request_type.value
        cascade_result = await classify_request_async(text, "text")
        cascade = cascade_result.request_type.value

        if truth == "safety":
            stats["safety_truth"] += 1
            if old == "safety":
                stats["old_safety_hit"] += 1
            if cascade == "safety":
                stats["cascade_safety_hit"] += 1
        else:
            if old == "safety":
                stats["old_safety_false"].append(text)
            if cascade == "safety":
                stats["cascade_safety_false"].append(text)

        if truth:
            stats["judged"] += 1
            if old == truth:
                stats["old_correct"] += 1
            if cascade == truth:
                stats["cascade_correct"] += 1

        if old != cascade:
            stats["disagreements"].append(
                {"text": text, "truth": truth, "old": old, "cascade": cascade}
            )

    cascade_logger.removeHandler(counter)
    cascade_logger.setLevel(prev_level)
    # Ходы, которые каскад резолвит ДО строки "resolved_by=" (L0 urgent/data_entry
    # ранний return) или которые упали в except и попали в classify_request
    # напрямую — тоже не безымянные проценты, а посчитанный остаток.
    stats["l0_early_or_error"] = stats["total"] - (
        stats["l1_hits"] + stats["l2_hits"] + stats["fallback_hits"]
    )

    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    args = parser.parse_args()

    rows = json.loads(args.labels.read_text(encoding="utf-8"))["labels"]

    stats = asyncio.run(evaluate(rows))

    print(f"размеченных сообщений: {stats['total']} (с истиной: {stats['judged']})")

    print(f"\n=== SAFETY (истинных: {stats['safety_truth']}) ===")
    print(f"  поймал старый роутер: {stats['old_safety_hit']}/{stats['safety_truth']}")
    print(f"  поймал каскад:        {stats['cascade_safety_hit']}/{stats['safety_truth']}")
    print(f"  ложных у старого:     {len(stats['old_safety_false'])}")
    for text in stats["old_safety_false"]:
        print(f"     - {text[:70]!r}")
    print(f"  ложных у каскада:     {len(stats['cascade_safety_false'])}")
    for text in stats["cascade_safety_false"]:
        print(f"     - {text[:70]!r}")

    judged = stats["judged"]
    print("\n=== ТОЧНОСТЬ ПО request_type ===")
    if judged:
        print(f"  старый роутер: {stats['old_correct']}/{judged} ({stats['old_correct'] / judged:.0%})")
        print(f"  каскад:        {stats['cascade_correct']}/{judged} ({stats['cascade_correct'] / judged:.0%})")

    total = stats["total"]
    print("\n=== КЕМ РЕЗОЛВЛЕНО (доля L2 — часть 9.2 манула, цель < 15%) ===")
    print(f"  L0 (urgent/data_entry) или ошибка каскада: {stats['l0_early_or_error']}/{total} ({stats['l0_early_or_error'] / total:.0%})")
    print(f"  L1:                                        {stats['l1_hits']}/{total} ({stats['l1_hits'] / total:.0%})")
    print(f"  L2:                                        {stats['l2_hits']}/{total} ({stats['l2_hits'] / total:.0%})")
    print(f"  откат на старый роутер (fallback):          {stats['fallback_hits']}/{total} ({stats['fallback_hits'] / total:.0%})")

    print(f"\n=== РАСХОЖДЕНИЯ (старый vs каскад): {len(stats['disagreements'])} ===")
    for item in stats["disagreements"][:30]:
        print(
            f"     - {item['text'][:55]!r} истина={item['truth']} "
            f"старый={item['old']} каскад={item['cascade']}"
        )
    if len(stats["disagreements"]) > 30:
        print(f"     ... и ещё {len(stats['disagreements']) - 30}")

    by_truth = Counter(_INTENT_TO_REQUEST_TYPE.get(r.get("intent")) for r in rows)
    print(f"\nраспределение истины: {dict(by_truth.most_common())}")


if __name__ == "__main__":
    main()
