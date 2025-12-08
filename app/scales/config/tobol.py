from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

RESOURCE_PATH = Path(__file__).resolve().parent.parent / "resources" / "tobol.md"


@dataclass(frozen=True)
class TobolItem:
    id: str
    section: str
    index: int
    section_title: str
    text: str


PROFILE_CODES = ["G", "R", "Z", "T", "I", "N", "M", "A", "S", "E", "P", "D"]

FORBID = "forbid"

PROFILE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "G": {"label": "Гармоничный", "description": "Адаптивное отношение к болезни с сохранением активности."},
    "R": {"label": "Эргопатический", "description": "Сосредоточенность на работе и привычной деятельности вопреки болезни."},
    "Z": {"label": "Анозогнозический", "description": "Отрицание тяжести болезни и ее последствий."},
    "T": {"label": "Тревожный", "description": "Выраженная тревога и опасения, связанные с заболеванием."},
    "I": {"label": "Ипохондрический", "description": "Фиксация на симптомах и поиске подтверждения серьезности болезни."},
    "N": {"label": "Неврастенический", "description": "Истощаемость, раздражительность и усталость на фоне болезни."},
    "M": {"label": "Меланхолический", "description": "Подавленность и пессимизм, сниженный эмоциональный фон."},
    "A": {"label": "Апатический", "description": "Равнодушие и безразличие к своему состоянию и окружению."},
    "S": {"label": "Сензитивный", "description": "Повышенная чувствительность к отношению окружающих."},
    "E": {"label": "Эгоцентрический", "description": "Стремление привлекать внимание к болезни и своим переживаниям."},
    "P": {"label": "Паранойяльный", "description": "Подозрительность и поиск виновных в возникновении заболевания."},
    "D": {"label": "Дисфорический", "description": "Раздражительность и вспышки гнева, нередко сочетающиеся с тоской."},
}

_CYRILLIC_TO_PROFILE = {
    "Г": "G",
    "Р": "R",
    "З": "Z",
    "Т": "T",
    "И": "I",
    "Н": "N",
    "М": "M",
    "А": "A",
    "С": "S",
    "Э": "E",
    "П": "P",
    "Д": "D",
}


def _parse_items() -> list[TobolItem]:
    lines = RESOURCE_PATH.read_text(encoding="utf-8").splitlines()
    heading_pattern = re.compile(r"^###\s+([IVXL]+)\.\s*(.+)$")
    items: list[TobolItem] = []
    current_section: str | None = None
    section_title = ""

    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("## Диагностический код опросника"):
            break

        heading_match = heading_pattern.match(line)
        if heading_match:
            current_section = heading_match.group(1)
            section_title = heading_match.group(2).strip()
            continue

        if current_section and re.match(r"^\d+\.\s+", line):
            idx_str, text = line.split(".", 1)
            index = int(idx_str)
            items.append(
                TobolItem(
                    id=f"{current_section}_{index}",
                    section=current_section,
                    index=index,
                    section_title=section_title,
                    text=text.strip(),
                )
            )

    return items


def _parse_coefficients(items: Iterable[TobolItem]) -> dict[str, dict[str, int | str]]:
    coeffs: dict[str, dict[str, int | str]] = {item.id: {} for item in items}
    lines = RESOURCE_PATH.read_text(encoding="utf-8").splitlines()

    in_tables = False
    current_topic: str | None = None
    header_codes: list[str] = []
    topic_pattern = re.compile(r"^###\s+Тема\s+([IVXL]+)")

    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("## Диагностический код опросника"):
            in_tables = True
            continue

        if not in_tables:
            continue

        topic_match = topic_pattern.match(line)
        if topic_match:
            current_topic = topic_match.group(1)
            header_codes = []
            continue

        if not current_topic or not line.startswith("|"):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue

        if cells[0].startswith("---"):
            continue

        if cells[0].startswith("№"):
            header_codes = [
                _CYRILLIC_TO_PROFILE.get(code.replace(":", ""), code) for code in cells[1:]
            ]
            continue

        row_label = cells[0].replace(":", "").strip()
        if not row_label or not row_label.isdigit():
            continue

        question_id = f"{current_topic}_{int(row_label)}"
        row_coeffs: dict[str, int | str] = {}
        for code, value in zip(header_codes, cells[1:]):
            if not code or code not in PROFILE_CODES:
                continue
            if value == "*":
                row_coeffs[code] = FORBID
            elif value:
                row_coeffs[code] = int(value)

        if question_id in coeffs:
            coeffs[question_id] = row_coeffs

    return coeffs


TOBOL_ITEMS: list[TobolItem] = _parse_items()
TOBOL_COEFFS: dict[str, dict[str, int | str]] = _parse_coefficients(TOBOL_ITEMS)

TOBOL_CONFIG: dict = {
    "code": "TOBOL",
    "title": "ТОБОЛ — Тип отношения к болезни",
    "version": "1.0",
    "questions": [
        {
            "id": item.id,
            "section": item.section,
            "section_title": item.section_title,
            "text": item.text,
            "options": [{"id": str(item.index), "text": item.text}],
        }
        for item in TOBOL_ITEMS
    ],
}

