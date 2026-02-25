"""KDQOL-SF 1.3 scoring algorithm.

Calculates subscale scores (0-100, higher = better) from raw responses.
Source: ТЗ Section 4 + resources/kdqol_sf_structure.json
"""

from __future__ import annotations

from statistics import mean
from typing import Optional

# ---------------------------------------------------------------------------
# Recode tables
# ---------------------------------------------------------------------------

# Physical functioning: q3a-3j  (1→0, 2→50, 3→100)
RECODE_PF = {1: 0.0, 2: 50.0, 3: 100.0}

# Yes/No items: q4a-4d, q5a-5c  (1=Да→0, 2=Нет→100)
RECODE_YESNO = {1: 0.0, 2: 100.0}

# 6-point frequency items q9 energy/emotions (1→0 ... 6→100)
RECODE_6PT = {1: 0.0, 2: 20.0, 3: 40.0, 4: 60.0, 5: 80.0, 6: 100.0}

# 6-point frequency reversed (1→100 ... 6→0): cognitive, social interaction
RECODE_6PT_REV = {1: 100.0, 2: 80.0, 3: 60.0, 4: 40.0, 5: 20.0, 6: 0.0}

# 5-point reversed (symptoms/effects: no problem=100)
RECODE_5PT_REV = {1: 100.0, 2: 75.0, 3: 50.0, 4: 25.0, 5: 0.0}

# Burden kidney (1→0 ... 5→100, then reverse)
RECODE_BURDEN = {1: 0.0, 2: 25.0, 3: 50.0, 4: 75.0, 5: 100.0}

# 4-point satisfaction (1→0, 2→33, 3→67, 4→100)
RECODE_4PT = {1: 0.0, 2: 33.0, 3: 67.0, 4: 100.0}

# Sleep q18a, 18c, 18d  (more often waking/drowsy=worse: 1→100, 5→0)
RECODE_SLEEP18 = {1: 100.0, 2: 75.0, 3: 50.0, 4: 25.0, 5: 0.0}

# Sleep q18b reversed (slept enough: 1=never→0, 5=always→100)
RECODE_SLEEP18B = {1: 0.0, 2: 25.0, 3: 50.0, 4: 75.0, 5: 100.0}

# Work status q16a-16b (1=Да-мешало→100 reversed per ТЗ: "recode 1->100, 2->0")
RECODE_WORK = {1: 100.0, 2: 0.0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply(table: dict[int, float], val: float) -> Optional[float]:
    return table.get(int(val))


def _mean_of(values: list[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(mean(vals), 2) if vals else None


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


def calculate_kdqol(
    responses: dict[str, float]
) -> dict[str, Optional[float]]:
    """Calculate KDQOL-SF 1.3 subscale scores from raw responses.

    Args:
        responses: mapping of question_id (e.g. "3a", "17") to raw answer value.

    Returns:
        dict of subscale_name → score (0-100) or None if insufficient data.
    """
    r = responses

    def get(qid: str) -> Optional[float]:
        v = r.get(qid)
        return float(v) if v is not None else None

    def recode(table: dict, qid: str) -> Optional[float]:
        v = get(qid)
        return _apply(table, v) if v is not None else None

    scores: dict[str, Optional[float]] = {}

    # physical_functioning (3a-3j)
    scores["physical_functioning"] = _mean_of(
        [recode(RECODE_PF, f"3{s}") for s in "abcdefghij"]
    )

    # role_physical (4a-4d)
    scores["role_physical"] = _mean_of(
        [recode(RECODE_YESNO, f"4{s}") for s in "abcd"]
    )

    # pain (7, 8)
    pain7 = {1: 100.0, 2: 80.0, 3: 60.0, 4: 40.0, 5: 20.0, 6: 0.0}
    pain8 = {1: 100.0, 2: 75.0, 3: 50.0, 4: 25.0, 5: 0.0}
    scores["pain"] = _mean_of([
        _apply(pain7, get("7")) if get("7") is not None else None,
        _apply(pain8, get("8")) if get("8") is not None else None,
    ])

    # general_health (1, 11a-11d)
    gh_q1  = {1: 100.0, 2: 75.0, 3: 50.0, 4: 25.0, 5: 0.0}
    gh_neg = {1: 0.0, 2: 25.0, 3: 50.0, 4: 75.0, 5: 100.0}
    gh_pos = {1: 100.0, 2: 75.0, 3: 50.0, 4: 25.0, 5: 0.0}
    scores["general_health"] = _mean_of([
        _apply(gh_q1,  get("1"))   if get("1")   is not None else None,
        _apply(gh_neg, get("11a")) if get("11a") is not None else None,
        _apply(gh_pos, get("11b")) if get("11b") is not None else None,
        _apply(gh_neg, get("11c")) if get("11c") is not None else None,
        _apply(gh_pos, get("11d")) if get("11d") is not None else None,
    ])

    # emotional_wellbeing (9b, 9c, 9d, 9f, 9h)
    scores["emotional_wellbeing"] = _mean_of(
        [recode(RECODE_6PT, q) for q in ["9b", "9c", "9d", "9f", "9h"]]
    )

    # role_emotional (5a-5c)
    scores["role_emotional"] = _mean_of(
        [recode(RECODE_YESNO, f"5{s}") for s in "abc"]
    )

    # social_functioning (6, 10)
    sf6  = {1: 100.0, 2: 75.0, 3: 50.0, 4: 25.0, 5: 0.0}
    sf10 = {1: 0.0, 2: 25.0, 3: 50.0, 4: 75.0, 5: 100.0}
    scores["social_functioning"] = _mean_of([
        _apply(sf6,  get("6"))  if get("6")  is not None else None,
        _apply(sf10, get("10")) if get("10") is not None else None,
    ])

    # energy_fatigue (9a, 9e, 9g, 9i)
    scores["energy_fatigue"] = _mean_of(
        [recode(RECODE_6PT, q) for q in ["9a", "9e", "9g", "9i"]]
    )

    # symptoms (14a-14m; 14m may be absent for HD patients)
    sym_items = ["14a","14b","14c","14d","14e","14f","14g",
                 "14h","14i","14j","14k","14l","14m"]
    scores["symptoms"] = _mean_of(
        [recode(RECODE_5PT_REV, q) for q in sym_items]
    )

    # effects_kidney (15a-15h)
    scores["effects_kidney"] = _mean_of(
        [recode(RECODE_5PT_REV, f"15{s}") for s in "abcdefgh"]
    )

    # burden_kidney (12a-12d, recode BURDEN then reverse)
    bk = _mean_of([recode(RECODE_BURDEN, f"12{s}") for s in "abcd"])
    scores["burden_kidney"] = round(100.0 - bk, 2) if bk is not None else None

    # work_status (16a-16b)
    scores["work_status"] = _mean_of(
        [recode(RECODE_WORK, f"16{s}") for s in "ab"]
    )

    # cognitive_function (13b, 13d, 13f)
    scores["cognitive_function"] = _mean_of(
        [recode(RECODE_6PT_REV, q) for q in ["13b", "13d", "13f"]]
    )

    # quality_social_interaction (13a, 13c normal; 13e reversed)
    scores["quality_social_interaction"] = _mean_of([
        recode(RECODE_6PT_REV, "13a"),
        recode(RECODE_6PT_REV, "13c"),
        recode(RECODE_6PT,     "13e"),   # 13e: ладили с людьми — reverse
    ])

    # sexual_function (20a, 20b — optional)
    sf2 = [recode(RECODE_4PT, "20a"), recode(RECODE_4PT, "20b")]
    scores["sexual_function"] = _mean_of(sf2) if any(v is not None for v in sf2) else None

    # sleep (17 * 10; 18a,18c,18d normal; 18b reversed)
    q17 = get("17")
    sleep_vals = [
        round(q17 * 10.0, 2) if q17 is not None else None,
        recode(RECODE_SLEEP18,  "18a"),
        recode(RECODE_SLEEP18B, "18b"),
        recode(RECODE_SLEEP18,  "18c"),
        recode(RECODE_SLEEP18,  "18d"),
    ]
    scores["sleep"] = _mean_of(sleep_vals)

    # social_support (19a, 19b)
    scores["social_support"] = _mean_of(
        [recode(RECODE_4PT, "19a"), recode(RECODE_4PT, "19b")]
    )

    # dialysis_staff_encouragement (21a-21d)
    scores["dialysis_staff_encouragement"] = _mean_of(
        [recode(RECODE_4PT, f"21{s}") for s in "abcd"]
    )

    # patient_satisfaction (22a-22h)
    scores["patient_satisfaction"] = _mean_of(
        [recode(RECODE_4PT, f"22{s}") for s in "abcdefgh"]
    )

    return scores


# ---------------------------------------------------------------------------
# Feedback module mapping
# ---------------------------------------------------------------------------

_SUBSCALE_TO_MODULE: dict[str, str] = {
    "sleep":                    "04_Сон",
    "symptoms":                 "Симптомы",
    "energy_fatigue":           "Энергия",
    "emotional_wellbeing":      "Эмоции",
    "burden_kidney":            "Бремя_болезни",
    "effects_kidney":           "Влияние_болезни",
    "physical_functioning":     "Физическая_активность",
    "social_functioning":       "Социальное_функционирование",
    "cognitive_function":       "Когнитивные_функции",
    "pain":                     "Боль",
    "general_health":           "Общее_здоровье",
}


def get_kdqol_feedback_module(scores: dict[str, Optional[float]]) -> Optional[str]:
    """Return education module code for the lowest-scoring subscale."""
    relevant = {k: v for k, v in scores.items() if v is not None and k in _SUBSCALE_TO_MODULE}
    if not relevant:
        return None
    return _SUBSCALE_TO_MODULE.get(min(relevant, key=lambda k: relevant[k]))
