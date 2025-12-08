from __future__ import annotations

from app.scales.calculators.hads import calculate_hads
from app.scales.calculators.kop_25a1 import calculate_kop_25a1
from app.scales.calculators.tobol import calculate_tobol

SCALE_CALCULATORS = {
    "HADS": calculate_hads,
    "KOP_25A1": calculate_kop_25a1,
    "KOP25A": calculate_kop_25a1,
    "TOBOL": calculate_tobol,
}


def get_scale_calculator(scale_code: str):
    return SCALE_CALCULATORS[scale_code]
