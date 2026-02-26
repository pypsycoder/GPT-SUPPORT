#!/usr/bin/env python
"""
Экспорт логов чата в CSV или JSON.

Использование:
    python scripts/export_chat_logs.py --output logs.csv
    python scripts/export_chat_logs.py --patient 5 --domain sleep --output sleep_p5.csv
    python scripts/export_chat_logs.py --date-from 2026-01-01 --date-to 2026-02-01 --output jan.csv
    python scripts/export_chat_logs.py --format json --output logs.json
    python scripts/export_chat_logs.py --no-content --output meta_only.csv

Запускать из корня проекта (GPT-SUPPORT/).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import datetime, date, time as dt_time
from pathlib import Path

# Корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text                         # noqa: E402
from core.db.session import async_session_factory   # noqa: E402


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_EXPORT_SQL = """
    SELECT
        lrl.id,
        lrl.patient_id,
        u.center_id::text                           AS center_id,
        lrl.created_at,
        cm_asst.domain                              AS domain,
        lrl.request_type,
        lrl.model_tier,
        lrl.tokens_input,
        lrl.tokens_output,
        lrl.response_time_ms,
        lrl.success,
        LEFT(cm_user.content, 200)                  AS question_preview,
        LEFT(cm_asst.content, 200)                  AS answer_preview
    FROM llm.llm_request_logs lrl
    LEFT JOIN users.users u ON u.id = lrl.patient_id
    LEFT JOIN LATERAL (
        SELECT content
        FROM llm.chat_messages
        WHERE patient_id = lrl.patient_id
          AND role = 'user'
          AND created_at BETWEEN lrl.created_at - INTERVAL '120 seconds'
                             AND lrl.created_at + INTERVAL '120 seconds'
        ORDER BY ABS(EXTRACT(EPOCH FROM created_at - lrl.created_at))
        LIMIT 1
    ) cm_user ON true
    LEFT JOIN LATERAL (
        SELECT content, domain
        FROM llm.chat_messages
        WHERE patient_id = lrl.patient_id
          AND role = 'assistant'
          AND created_at BETWEEN lrl.created_at - INTERVAL '120 seconds'
                             AND lrl.created_at + INTERVAL '120 seconds'
        ORDER BY ABS(EXTRACT(EPOCH FROM created_at - lrl.created_at))
        LIMIT 1
    ) cm_asst ON true
    WHERE {where}
    ORDER BY lrl.created_at DESC
"""

_COLUMNS_FULL = [
    "id", "patient_id", "center_id", "created_at",
    "domain", "request_type", "model_tier",
    "tokens_input", "tokens_output", "response_time_ms", "success",
    "question_preview", "answer_preview",
]

_COLUMNS_META = [
    "id", "patient_id", "center_id", "created_at",
    "domain", "request_type", "model_tier",
    "tokens_input", "tokens_output", "response_time_ms", "success",
]


# ---------------------------------------------------------------------------
# DB fetch
# ---------------------------------------------------------------------------

async def fetch_rows(args: argparse.Namespace) -> list:
    where_parts = ["1=1"]
    params: dict = {}

    if args.patient:
        where_parts.append("lrl.patient_id = :patient_id")
        params["patient_id"] = args.patient

    if args.center:
        where_parts.append("u.center_id = :center_id::uuid")
        params["center_id"] = args.center

    if args.domain:
        where_parts.append("cm_asst.domain = :domain")
        params["domain"] = args.domain

    if args.model:
        where_parts.append("lrl.model_tier = :model_tier")
        params["model_tier"] = args.model

    if args.date_from:
        try:
            df = datetime.combine(date.fromisoformat(args.date_from), dt_time.min)
        except ValueError:
            print(f"Ошибка: неверный формат --date-from '{args.date_from}' (ожидается YYYY-MM-DD)")
            sys.exit(1)
        where_parts.append("lrl.created_at >= :date_from")
        params["date_from"] = df

    if args.date_to:
        try:
            dt = datetime.combine(date.fromisoformat(args.date_to), dt_time.max)
        except ValueError:
            print(f"Ошибка: неверный формат --date-to '{args.date_to}' (ожидается YYYY-MM-DD)")
            sys.exit(1)
        where_parts.append("lrl.created_at <= :date_to")
        params["date_to"] = dt

    where_str = " AND ".join(where_parts)
    sql = text(_EXPORT_SQL.format(where=where_str))

    print("Подключение к БД...")
    async with async_session_factory() as session:
        result = await session.execute(sql, params)
        rows = result.mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------

def write_csv(rows: list, output: Path, columns: list[str]) -> None:
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for i, row in enumerate(rows, 1):
            writer.writerow([
                row.get(c, "") if row.get(c) is not None else ""
                for c in columns
            ])
            if i % 500 == 0:
                print(f"  Записано {i} строк...")


def write_json(rows: list, output: Path, columns: list[str]) -> None:
    def _serialize(row: dict) -> dict:
        out = {c: row.get(c) for c in columns}
        if out.get("created_at") is not None:
            out["created_at"] = out["created_at"].isoformat()
        if out.get("success") is not None:
            out["success"] = bool(out["success"])
        return out

    data = [_serialize(r) for r in rows]
    with output.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Экспорт логов чата GPT Health Support",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--output",    required=True, help="Путь к файлу вывода (напр. logs.csv)")
    parser.add_argument("--patient",   type=int,   default=None, help="ID пациента")
    parser.add_argument("--center",    default=None, help="UUID центра диализа")
    parser.add_argument("--domain",    default=None, help="Домен: sleep|emotion|routine|stress|self_care|social|motivation")
    parser.add_argument("--model",     default=None, help="Модель: lite|pro|max")
    parser.add_argument("--date-from", dest="date_from", default=None, help="Дата начала YYYY-MM-DD")
    parser.add_argument("--date-to",   dest="date_to",   default=None, help="Дата конца YYYY-MM-DD")
    parser.add_argument("--format",    default="csv", choices=["csv", "json"], help="Формат вывода (default: csv)")
    parser.add_argument("--no-content", dest="no_content", action="store_true",
                        help="Не включать тексты сообщений (только метаданные)")
    return parser.parse_args()


def main() -> None:
    args   = parse_args()
    output = Path(args.output)
    columns = _COLUMNS_META if args.no_content else _COLUMNS_FULL

    # Fetch data
    rows = asyncio.run(fetch_rows(args))

    if not rows:
        print("Нет записей по заданным фильтрам.")
        return

    print(f"Получено {len(rows)} записей, сохраняю в {output}...")

    if args.format == "json":
        write_json(rows, output, columns)
    else:
        write_csv(rows, output, columns)

    print(f"Экспортировано {len(rows)} записей → {output}")


if __name__ == "__main__":
    main()
