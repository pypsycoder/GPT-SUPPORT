#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка согласованности тестов и уроков.

Зачем это существует
--------------------
Дважды подряд случилась одна и та же ошибка: урок исправляли, а тест к нему
оставался со старым содержанием в качестве правильного ответа.

  08.08.2026 — после правки нефроуроков в тестах остались Hb 110–120,
               фосфор 1,13–1,78, прибавка 2–3%, Kt/V 1,2.
  30.08.2026 — после удаления из урока «Эмоции» утверждения про «90 секунд»
               в тесте остались два вопроса, проверявших именно его.

Во втором случае тест активно закреплял утверждение, которое мы признали
недостоверным. Вывод, записанный в трекер: это должна быть не строка чек-листа,
а скрипт.

Что делает
----------
1. Валидирует структуру каждого теста (поля, диапазон correct_option,
   отсутствие дублей вариантов, уникальность order_index).
2. Проверяет коллизии test_id между блоками — id сквозной по проекту.
3. Считает распределение правильного ответа по позициям (правило №2:
   тест не должен проходиться угадыванием одной позиции).
   Дополнительно проверяет, что test_id лежит в диапазоне своего блока
   (1NN — психология, 2NN — гемодиализ, 3NN — сквозной) и совпадает
   с числовым префиксом имени файла.
4. Главное: вытаскивает из вопросов и правильных ответов числовые токены
   и проверяет, что они встречаются в тексте соответствующего урока.
   Число, которого в уроке нет, — кандидат на устаревшее значение.

Ограничение
-----------
Пункт 4 — эвристика, а не доказательство. Он ловит расхождения по числам,
но не по формулировкам. Числа — самый частый и самый опасный вид расхождения,
поэтому начинаем с них. Результат требует глазами просмотреть список
«чисел не найдено в уроке» — часть из них законный шум (годы, номера пунктов,
числа в дистракторах).

Уроки, лежащие в черновиках вне content/, в маппинге помечены как None —
для них проверка структуры выполняется, сверка по числам пропускается.

Запуск
------
    python scripts/check_tests_vs_lessons.py
    python scripts/check_tests_vs_lessons.py --strict   # ненулевой код возврата при находках
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDU = ROOT / "content" / "education"

# Тест -> урок. None означает, что урок ещё в черновиках вне content/.
MAPPING: dict[str, str | None] = {
    # 1NN — психология
    "psychology/tests/101_Стресс-тест.md": "psychology/101.Стресс.md",
    "psychology/tests/102_Эмоции-тест.md": "psychology/102.Эмоции.md",
    "psychology/tests/103_Тревога-тест.md": "psychology/103.Тревога.md",
    "psychology/tests/104_Сон-тест.md": "psychology/104.Сон.md",
    "psychology/tests/105_Копинг-тест.md": "psychology/105.Копинг-стратегии.md",
    "psychology/tests/106_Мотивация-тест.md": "psychology/106.Мотивация.md",
    "psychology/tests/107_Когнитивные-тест.md": "psychology/107.Когнитивные способности.md",
    "psychology/tests/108_Выгорание-тест.md": "psychology/108.Эмоциональное выгорание.md",
    "psychology/tests/109_Адаптация-тест.md": "psychology/109.Адаптации к хронической болезни.md",
    "psychology/tests/110_Тело_и_образ-тест.md": None,
    # 2NN — гемодиализ
    "nephrology/tests/201_Что_такое_гемодиализ-тест.md": None,
    "nephrology/tests/202_Питание-тест.md": "nephrology/202_Питание.md",
    "nephrology/tests/203_Жидкость-тест.md": "nephrology/203_Жидкость.md",
    "nephrology/tests/204_Препараты-тест.md": "nephrology/204_Препараты.md",
    "nephrology/tests/205_Активность-тест.md": "nephrology/205_Активность.md",
    "nephrology/tests/206_Фистула-тест.md": "nephrology/206_Фистула.md",
    "nephrology/tests/207_Симптомы-тест.md": "nephrology/207_Симптомы.md",
    "nephrology/tests/208_Лаборатория-тест.md": "nephrology/208_Лаборатория.md",
    "nephrology/tests/209_Жизнь_с_диализом-тест.md": "nephrology/209_Жизнь_с_диализом.md",
    "nephrology/tests/210_Катетер-тест.md": None,
    "nephrology/tests/211_МКН-тест.md": None,
    "nephrology/tests/212_Параметры_процедуры-тест.md": None,
    "nephrology/tests/213_Поездки-тест.md": None,
    # 3NN — сквозной блок
    "crosscutting/tests/301_Кто_за_что_отвечает-тест.md": None,
    "crosscutting/tests/302_Разговор_с_врачом-тест.md": None,
    "crosscutting/tests/303_Оценка_советов-тест.md": None,
}

REQUIRED = ("test_id", "order_index", "question_text",
            "option_1", "option_2", "option_3", "option_4", "correct_option")

# Числа вида 1,4 / 12 / 800–1000. Одиночные 1–4 отбрасываем: это нумерация, не значения.
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
NOISE = {"1", "2", "3", "4", "5", "10", "100"}


def normalize(num: str) -> str:
    return num.replace(",", ".").rstrip("0").rstrip(".") if "," in num or "." in num else num


def lesson_numbers(text: str) -> set[str]:
    return {normalize(n) for n in NUM_RE.findall(text)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="вернуть код 1, если есть структурные ошибки или числа-сироты")
    args = ap.parse_args()

    structural: list[str] = []
    orphan_numbers: list[str] = []
    by_id: dict[int, set[str]] = collections.defaultdict(set)
    positions: collections.Counter = collections.Counter()
    total_q = 0
    checked_pairs = 0
    skipped: list[str] = []

    for rel, lesson_rel in MAPPING.items():
        path = EDU / rel
        if not path.exists():
            structural.append(f"{rel}: файла нет")
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            structural.append(f"{rel}: некорректный JSON — {exc}")
            continue

        seen_order: set[int] = set()
        for q in data:
            total_q += 1
            missing = [k for k in REQUIRED if k not in q]
            if missing:
                structural.append(f"{rel} #{q.get('order_index')}: нет полей {missing}")
                continue
            if q["correct_option"] not in (1, 2, 3, 4):
                structural.append(f"{rel} #{q['order_index']}: correct_option={q['correct_option']}")
            opts = [q[f"option_{i}"] for i in range(1, 5)]
            if len(set(opts)) < 4:
                structural.append(f"{rel} #{q['order_index']}: повторяются варианты ответа")
            if q["order_index"] in seen_order:
                structural.append(f"{rel}: order_index {q['order_index']} встречается дважды")
            seen_order.add(q["order_index"])
            block_expected = {"psychology": 1, "nephrology": 2, "crosscutting": 3}[rel.split("/")[0]]
            if q["test_id"] // 100 != block_expected:
                structural.append(
                    f"{rel} #{q['order_index']}: test_id {q['test_id']} вне диапазона блока {block_expected}NN")
            file_prefix = int(os.path.basename(rel).split("_")[0])
            if q["test_id"] != file_prefix:
                structural.append(
                    f"{rel} #{q['order_index']}: test_id {q['test_id']} не совпадает с именем файла ({file_prefix})")
            by_id[q["test_id"]].add(rel)
            positions[q["correct_option"]] += 1

        if lesson_rel is None:
            skipped.append(rel)
            continue

        lesson_path = EDU / lesson_rel
        if not lesson_path.exists():
            structural.append(f"{rel}: урок {lesson_rel} не найден")
            continue

        known = lesson_numbers(lesson_path.read_text(encoding="utf-8"))
        checked_pairs += 1
        for q in data:
            if "correct_option" not in q:
                continue
            probe = q["question_text"] + " " + q[f"option_{q['correct_option']}"]
            for raw in NUM_RE.findall(probe):
                if raw in NOISE:
                    continue
                if normalize(raw) not in known:
                    orphan_numbers.append(
                        f"{rel} #{q['order_index']}: «{raw}» нет в уроке — {q['question_text'][:70]}"
                    )

    collisions = {k: sorted(v) for k, v in by_id.items() if len(v) > 1}

    print(f"Тестов: {len(MAPPING)} | вопросов: {total_q} | сверено с уроком: {checked_pairs}")
    print(f"Пропущено (урок ещё в черновиках): {len(skipped)}")

    print("\nРаспределение правильного ответа:")
    for pos in (1, 2, 3, 4):
        share = positions[pos] * 100 // total_q if total_q else 0
        flag = "  ← перекос" if share >= 40 or share <= 10 else ""
        print(f"  вариант {pos}: {positions[pos]:>3} ({share}%){flag}")

    print("\nКоллизии test_id:", collisions or "нет")

    print(f"\nСтруктурные ошибки: {len(structural)}")
    for line in structural:
        print("  ✗", line)

    print(f"\nЧисла из тестов, отсутствующие в уроке: {len(orphan_numbers)}")
    print("  (эвристика — проверьте глазами, часть находок законна)")
    for line in orphan_numbers:
        print("  ?", line)

    if args.strict and (structural or orphan_numbers or collisions):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
