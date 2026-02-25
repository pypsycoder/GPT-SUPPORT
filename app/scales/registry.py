from __future__ import annotations

from app.scales.calculators.hads import calculate_hads
from app.scales.calculators.kop_25a1 import calculate_kop_25a1
from app.scales.calculators.psqi import calculate_psqi
from app.scales.calculators.wcq_lazarus import calculate_wcq_lazarus

SCALE_CALCULATORS = {
    "HADS": calculate_hads,
    "KOP_25A1": calculate_kop_25a1,
    "KOP25A": calculate_kop_25a1,
    "PSQI": calculate_psqi,
    "WCQ_LAZARUS": calculate_wcq_lazarus,
}


def get_scale_calculator(scale_code: str):
    return SCALE_CALCULATORS[scale_code]
