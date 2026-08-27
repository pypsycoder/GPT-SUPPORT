"""Разовый скрипт: собрать корпус для семантического crisis-детектора из
отчётов ночного прогона patient-sim (`test-results/patient-sim/*.md`).

Не часть прод-кода. Парсит markdown-отчёты, вытаскивает реплики пациента
вместе со сценарием и меткой "ЭСКАЛАЦИЯ"/её отсутствием, дедуплицирует,
раскладывает по двум спискам:
  - позитив: реплики из s01/s02 (суицидальный риск), которые ДОЛЖНЫ
    эскалировать — вне зависимости от того, эскалировали ли они в
    конкретном прогоне (это то, что мы ХОТИМ ловить, не то, что поймал
    текущий детектор);
  - hard_negative: реплики из s03-s08 (НЕ суицидальный риск, но часто
    драматично/тревожно звучат) — то, на чём семантический детектор не
    должен срабатывать.

Печатает Python-литералы, готовые к вставке в crisis_prototypes.py —
скрипт только собирает сырьё, финальную модерацию (какие реплики реально
годятся как прототипы) делает человек/агент вручную.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parents[2] / "test-results" / "patient-sim"

# Ходовая строка: "- **Пациент** _(ход N, источник: X)_: текст"
TURN_RE = re.compile(
    r"^- \*\*Пациент\*\* _\(ход \d+, источник: \w+\)_: (?P<text>.+?)\s*$"
)
SCENARIO_RE = re.compile(r"^### (?P<sid>s\d\d_\w+)")

SUICIDE_SCENARIOS = {"s01_suicide_indirect", "s02_suicide_explicit"}
NEGATIVE_SCENARIOS = {
    "s03_vitals_false_positive",
    "s04_non_adherent",
    "s05_anxious",
    "s06_denial",
    "s07_comorbid_dose",
    "s08_elderly_confused",
}


def parse_file(path: Path) -> list[tuple[str, str]]:
    """Вернуть [(scenario_id, patient_text), ...] для всех ходов файла."""
    out: list[tuple[str, str]] = []
    current_scenario = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = SCENARIO_RE.match(line)
        if m:
            current_scenario = m.group("sid")
            continue
        m = TURN_RE.match(line)
        if m and current_scenario:
            out.append((current_scenario, m.group("text").strip()))
    return out


def main() -> None:
    files = sorted(REPORTS_DIR.glob("*.md"))
    files = [f for f in files if f.name != "overnight-log.md"]

    positive: dict[str, str] = {}  # text -> scenario (dedup by text)
    negative: dict[str, str] = {}

    for f in files:
        for scenario, text in parse_file(f):
            if scenario in SUICIDE_SCENARIOS:
                positive[text] = scenario
            elif scenario in NEGATIVE_SCENARIOS:
                negative[text] = scenario

    out_path = Path(__file__).resolve().parent / "_corpus_raw.txt"
    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write("\n# === ПОЗИТИВ (суицидальный риск, должен ловиться) ===\n")
        for text, scenario in sorted(positive.items(), key=lambda kv: kv[1]):
            out.write(f"    ({text!r}, {scenario!r}),\n")

        out.write("\n# === HARD NEGATIVE (не суицидальный риск) ===\n")
        for text, scenario in sorted(negative.items(), key=lambda kv: kv[1]):
            out.write(f"    ({text!r}, {scenario!r}),\n")

    stats_path = Path(__file__).resolve().parent / "_corpus_stats.txt"
    with stats_path.open("w", encoding="utf-8", newline="\n") as stats:
        stats.write(f"Файлов обработано: {len(files)}\n")
        stats.write(f"Позитив (s01/s02), уникальных реплик: {len(positive)}\n")
        stats.write(f"Hard-negative (s03-s08), уникальных реплик: {len(negative)}\n")


if __name__ == "__main__":
    main()
