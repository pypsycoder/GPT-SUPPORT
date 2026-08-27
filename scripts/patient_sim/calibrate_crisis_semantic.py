"""Разовый скрипт калибровки threshold/margin для crisis_semantic.py.

Leave-one-out по всему корпусу crisis_prototypes.py: для каждого примера
считаем эмбеддинг, ищем ближайший позитив/негатив СРЕДИ ОСТАЛЬНЫХ (не
включая сам пример), проверяем на сетке threshold/margin, какая
комбинация даёт наименьшее число ошибок обоих типов (пропуск позитива /
ложное срабатывание на негативе).

Не часть прод-кода, не гоняется в CI — печатает отчёт и всё.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment  # noqa: E402

load_environment()

from app.llm.crisis_prototypes import NEGATIVE_MINED, POSITIVE_DRAFTED, POSITIVE_MINED  # noqa: E402
from app.llm.embeddings import cosine_similarity, get_text_embeddings_batch  # noqa: E402


async def main() -> None:
    positive_texts = [*POSITIVE_MINED, *POSITIVE_DRAFTED]
    negative_texts = NEGATIVE_MINED

    print(f"Эмбеддинг {len(positive_texts)} позитивных...", file=sys.stderr)
    pos_vecs = await get_text_embeddings_batch(positive_texts)
    print(f"Эмбеддинг {len(negative_texts)} негативных...", file=sys.stderr)
    neg_vecs = await get_text_embeddings_batch(negative_texts)

    pos_items = list(zip(positive_texts, pos_vecs))
    neg_items = list(zip(negative_texts, neg_vecs))

    # Для каждого позитива: leave-one-out ближайший позитив (среди остальных
    # позитивов) и ближайший негатив (все негативы — они не "он сам").
    pos_self_sim: list[float] = []
    pos_neg_sim: list[float] = []
    for i, (text, vec) in enumerate(pos_items):
        others = [v for j, (_, v) in enumerate(pos_items) if j != i]
        best_pos = max(cosine_similarity(vec, v) for v in others) if others else 0.0
        best_neg = max(cosine_similarity(vec, v) for _, v in neg_items)
        pos_self_sim.append(best_pos)
        pos_neg_sim.append(best_neg)

    # Для каждого негатива: ближайший позитив (все) и ближайший негатив
    # (leave-one-out среди остальных негативов).
    neg_pos_sim: list[float] = []
    neg_self_sim: list[float] = []
    for i, (text, vec) in enumerate(neg_items):
        best_pos = max(cosine_similarity(vec, v) for _, v in pos_items)
        others = [v for j, (_, v) in enumerate(neg_items) if j != i]
        best_neg = max(cosine_similarity(vec, v) for v in others) if others else 0.0
        neg_pos_sim.append(best_pos)
        neg_self_sim.append(best_neg)

    print("\n=== Сетка threshold x margin ===")
    print(f"{'thr':>5} {'margin':>7} {'pos_recall':>11} {'neg_false_pos':>14} {'пропущено':>10} {'ложных':>8}")
    for threshold in (0.65, 0.68, 0.70, 0.72, 0.75, 0.78, 0.80, 0.82, 0.85):
        for margin in (0.0, 0.02, 0.03, 0.05, 0.08):
            pos_hits = sum(
                1
                for best_pos, best_neg in zip(pos_self_sim, pos_neg_sim)
                if best_pos >= threshold and (best_pos - best_neg) >= margin
            )
            neg_false_pos = sum(
                1
                for best_pos, best_neg in zip(neg_pos_sim, neg_self_sim)
                if best_pos >= threshold and (best_pos - best_neg) >= margin
            )
            pos_recall = pos_hits / len(pos_items)
            neg_fp_rate = neg_false_pos / len(neg_items)
            print(
                f"{threshold:5.2f} {margin:7.2f} {pos_recall:11.2%} {neg_fp_rate:14.2%} "
                f"{len(pos_items) - pos_hits:10d} {neg_false_pos:8d}"
            )

    # Худшие случаи на разумной средней точке — что именно пропускается/ложно срабатывает.
    print("\n=== Позитивы с самым низким best_pos_sim (кандидаты на пропуск) ===")
    ranked = sorted(zip(positive_texts, pos_self_sim, pos_neg_sim), key=lambda t: t[1])
    for text, best_pos, best_neg in ranked[:5]:
        print(f"  best_pos={best_pos:.3f} best_neg={best_neg:.3f} margin={best_pos-best_neg:+.3f} | {text[:70]}")

    print("\n=== Негативы с самым высоким best_pos_sim (кандидаты на ложное срабатывание) ===")
    ranked_neg = sorted(zip(negative_texts, neg_pos_sim, neg_self_sim), key=lambda t: -t[1])
    for text, best_pos, best_neg in ranked_neg[:8]:
        print(f"  best_pos={best_pos:.3f} best_neg={best_neg:.3f} margin={best_pos-best_neg:+.3f} | {text[:70]}")


if __name__ == "__main__":
    asyncio.run(main())
