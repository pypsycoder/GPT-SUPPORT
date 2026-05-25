from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment


DEFAULT_QUERIES = [
    "Как наладить обычный режим дня и бытовую рутину?",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run standalone RAG debug evaluation.")
    parser.add_argument("--patient-id", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--report-dir", default="LLM_test/reports")
    parser.add_argument("--query", action="append", dest="queries")
    return parser.parse_args()


def _classify_candidate(query: str, candidate: dict[str, object]) -> str:
    title = str(candidate.get("lesson_title", "")).lower()
    overlap = candidate.get("overlap_tokens") or []
    if overlap:
        return "good"
    if any(token in title for token in ("сон", "тревог", "стресс", "эмоц", "рут", "диализ", "устал")):
        return "borderline"
    return "bad"


def _report_name() -> str:
    return f"rag_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _clip_fragment(text: str, limit: int = 240) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _build_rag_context_lines(modules: list[dict[str, object]], top_k: int) -> list[str]:
    lines: list[str] = []
    for module in modules[:top_k]:
        fragment = _clip_fragment(str(module.get("chunk", "")))
        lines.append(f"Урок «{module['title']}». Релевантный фрагмент: {fragment}")
    return lines


async def main() -> int:
    args = _parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    load_environment()

    from app.rag.retriever import retrieve_relevant_modules_with_meta
    from core.db.session import async_session_factory

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_base = _report_name()

    queries = args.queries or list(DEFAULT_QUERIES)
    payload: dict[str, object] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "patient_id": args.patient_id,
        "top_k": args.top_k,
        "queries": [],
    }

    async with async_session_factory() as db:
        for query in queries:
            retrieval = await retrieve_relevant_modules_with_meta(
                query=query,
                patient_id=args.patient_id,
                db=db,
                top_k=args.top_k,
            )
            debug = retrieval.get("debug", {})
            raw_candidates = list(debug.get("raw_candidates", []))
            selected_candidates = list(debug.get("selected_candidates", []))
            payload["queries"].append(
                {
                    "query": query,
                    "backend": retrieval["meta"].get("backend_selected") or retrieval["meta"].get("backend"),
                    "meta": retrieval["meta"],
                    "raw_candidates": raw_candidates,
                    "selected_candidates": selected_candidates,
                    "modules": retrieval["modules"],
                    "rag_context": _build_rag_context_lines(retrieval["modules"], args.top_k),
                    "candidate_labels": [
                        {
                            "lesson_id": candidate["lesson_id"],
                            "lesson_title": candidate["lesson_title"],
                            "hybrid_score": candidate["hybrid_score"],
                            "label": _classify_candidate(query, candidate),
                        }
                        for candidate in raw_candidates[: args.top_k]
                    ],
                }
            )

    json_path = report_dir / f"{report_base}.json"
    md_path = report_dir / f"{report_base}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        f"# RAG Debug Eval {report_base}",
        "",
        f"- patient_id: `{args.patient_id}`",
        f"- top_k: `{args.top_k}`",
        f"- generated_at: `{payload['generated_at']}`",
        "",
        "## Criteria",
        "",
        "- good: top-1 тематически релевантен и содержит usable fragment.",
        "- bad: в top-2 есть явно чужая тема или в контекст уходит только общий CTA.",
        "",
    ]

    for item in payload["queries"]:
        md_lines.extend(
            [
                f"## Query: {item['query']}",
                "",
                f"- backend: `{item['backend']}`",
                f"- candidate_rows: `{item['meta'].get('candidate_rows', 0)}`",
                f"- embedding_ms: `{item['meta'].get('embedding_request_ms', 0)}`",
                f"- vector_ms: `{item['meta'].get('vector_search_ms', 0)}`",
                "",
                "### Top Candidates",
                "",
            ]
        )
        for idx, candidate in enumerate(item["raw_candidates"][: args.top_k], start=1):
            reasons = candidate.get("selection_reasons") or candidate.get("rerank_reasons") or []
            md_lines.extend(
                [
                    f"{idx}. `{candidate['lesson_title']}` lesson_id=`{candidate['lesson_id']}` card_index=`{candidate['card_index']}`",
                    f"   vector=`{candidate['vector_similarity']}` hybrid=`{candidate['hybrid_score']}` overlap=`{candidate['overlap_tokens']}` section=`{candidate['section_name']}`",
                    f"   why: `{'; '.join(reasons)}`",
                    f"   text: {candidate['chunk_preview']}",
                    "",
                ]
            )
        md_lines.append("### rag_context")
        md_lines.append("")
        for line in item["rag_context"]:
            md_lines.append(f"- {line}")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"Saved JSON report to {json_path}")
    print(f"Saved MD report to {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
