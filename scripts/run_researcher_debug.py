from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(env_file)

from app.llm.agent_v2 import generate_response_v2
from app.llm.errors import LLMConfigurationError, LLMError
from app.llm.memory import st_memory_store
from app.llm.router import classify_request
from app.llm.trace_humanizer import build_human_trace
from app.models.llm import ChatMessage
from app.researchers import crud as researcher_crud
from app.researchers.router import (
    _apply_forced_model_tier,
    _build_debug_report_markdown,
    _next_debug_report_path,
)
from app.researchers.schemas import HumanTraceSection
from core.db.session import async_session_factory


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a repeatable researcher debug scenario and save an .md report.",
    )
    parser.add_argument("--patient-id", type=int, required=True, help="Patient ID for the scenario.")
    parser.add_argument(
        "--tier",
        default="lite",
        choices=["lite", "pro", "max"],
        help="Forced model tier for the scenario.",
    )
    parser.add_argument(
        "--message",
        action="append",
        dest="messages",
        help="Message to send. Repeat the flag for multiple turns.",
    )
    parser.add_argument(
        "--messages-file",
        type=Path,
        help="UTF-8 text file with one patient message per line.",
    )
    parser.add_argument("--session-id", help="Optional fixed debug session id.")
    parser.add_argument("--thread-id", default="main", help="Debug thread id.")
    parser.add_argument(
        "--persist-messages",
        action="store_true",
        help="Persist user/assistant chat messages into the database.",
    )
    parser.add_argument(
        "--keep-memory",
        action="store_true",
        help="Keep in-memory ST memory for the chosen session instead of clearing it before the run.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue the scenario after an LLM/runtime error and still save the full partial report.",
    )
    return parser.parse_args()


def _load_messages(args: argparse.Namespace) -> list[str]:
    messages: list[str] = []
    for item in args.messages or []:
        text = str(item).strip()
        if text:
            messages.append(text)

    if args.messages_file:
        raw = args.messages_file.read_text(encoding="utf-8")
        for line in raw.splitlines():
            text = line.strip()
            if text:
                messages.append(text)

    if not messages:
        raise SystemExit("No scenario messages provided. Use --message or --messages-file.")

    return messages


def _patient_label(patient: Any) -> str:
    if patient is None:
        return "-"
    patient_number = getattr(patient, "patient_number", None)
    full_name = getattr(patient, "full_name", None)
    if patient_number and full_name:
        return f"#{patient_number} {full_name}"
    return str(full_name or patient_number or "-")


def _human_trace_payload(diagnostics_json: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        HumanTraceSection(
            title=str(section.get("title") or "Trace"),
            items=[str(item) for item in section.get("items") or []],
        ).model_dump()
        for section in build_human_trace(diagnostics_json)
    ]


@dataclass(slots=True)
class TurnRunResult:
    ok: bool
    response: str
    diagnostics_json: dict[str, Any]
    human_trace: list[dict[str, Any]]
    requested_model_tier: str | None
    actual_model_tier: str | None
    account_id: str | None
    request_type: str | None
    supervisor_state: dict[str, Any] | None
    supervisor_state_delta: dict[str, Any]
    pending_st_memory: list[dict[str, Any]]
    pending_lt_memory: list[dict[str, Any]]
    memory_before: list[dict[str, Any]]
    memory_after: list[dict[str, Any]]


async def _run_turn(
    *,
    db: AsyncSession,
    patient_id: int,
    message: str,
    tier: str,
    session_id: str,
    thread_id: str,
    supervisor_state: dict[str, Any] | None,
    persist_messages: bool,
) -> TurnRunResult:
    from app.llm.morning_service import get_daily_context_for_llm

    memory_before = st_memory_store.read(
        patient_id=patient_id,
        session_id=session_id,
        thread_id=thread_id,
    )
    daily_ctx = await get_daily_context_for_llm(patient_id, db)

    router_result = _apply_forced_model_tier(classify_request(message, "text"), tier)

    try:
        llm_result = await generate_response_v2(
            patient_id=patient_id,
            user_input=message,
            router_result=router_result,
            context={
                "source": "text",
                "daily_context": daily_ctx,
                "session_id": session_id,
                "thread_id": thread_id,
                "st_memory": memory_before,
                "supervisor_state": supervisor_state,
                "strict_model_tier": True,
            },
            db=db,
        )
    except LLMConfigurationError as exc:
        raise SystemExit(str(exc)) from exc
    except LLMError as exc:
        diagnostics_json = dict(getattr(exc, "diagnostics", {}) or {})
        return TurnRunResult(
            ok=False,
            response=f"Ошибка debug-чата: {exc}",
            diagnostics_json=diagnostics_json,
            human_trace=_human_trace_payload(diagnostics_json),
            requested_model_tier=router_result.model_tier.value,
            actual_model_tier=None,
            account_id=None,
            request_type=router_result.request_type.value,
            supervisor_state=supervisor_state,
            supervisor_state_delta={},
            pending_st_memory=[],
            pending_lt_memory=[],
            memory_before=memory_before,
            memory_after=memory_before,
        )

    pending_st_memory = list(llm_result.get("pending_st_memory") or [])
    pending_lt_memory = list(llm_result.get("pending_lt_memory") or [])
    memory_after = st_memory_store.write(
        patient_id=patient_id,
        session_id=session_id,
        thread_id=thread_id,
        updates=pending_st_memory,
    )

    if persist_messages:
        db.add(
            ChatMessage(
                patient_id=patient_id,
                role="user",
                content=message,
                tokens_used=0,
                model_used=None,
                domain=llm_result.get("domain"),
                request_type=router_result.request_type.value,
            )
        )
        db.add(
            ChatMessage(
                patient_id=patient_id,
                role="assistant",
                content=llm_result["response"],
                tokens_used=int(llm_result.get("tokens_input", 0)) + int(llm_result.get("tokens_output", 0)),
                model_used=llm_result.get("model"),
                domain=llm_result.get("domain"),
                request_type=router_result.request_type.value,
                is_read=False,
            )
        )
        await db.commit()

    diagnostics_json = dict(llm_result.get("diagnostics") or {})
    return TurnRunResult(
        ok=True,
        response=str(llm_result["response"]),
        diagnostics_json=diagnostics_json,
        human_trace=_human_trace_payload(diagnostics_json),
        requested_model_tier=llm_result.get("requested_model_tier"),
        actual_model_tier=llm_result.get("actual_model_tier"),
        account_id=llm_result.get("account_id"),
        request_type=router_result.request_type.value,
        supervisor_state=llm_result.get("supervisor_state"),
        supervisor_state_delta=dict(llm_result.get("supervisor_state_delta") or {}),
        pending_st_memory=pending_st_memory,
        pending_lt_memory=pending_lt_memory,
        memory_before=memory_before,
        memory_after=memory_after,
    )


def _print_turn_summary(turn_number: int, turn_payload: dict[str, Any]) -> None:
    graph = dict(turn_payload.get("diagnostics_json", {}).get("supervisor", {}).get("goal_analysis", {}).get("router_card") or {})
    phase = graph.get("phase") or "-"
    status = graph.get("status") or "-"
    action = graph.get("next_action") or "-"
    reply = str(turn_payload.get("assistant_reply") or "")
    preview = " ".join(reply.split())
    if len(preview) > 120:
        preview = preview[:117] + "..."
    print(f"[turn {turn_number}] phase={phase} status={status} action={action}")
    print(f"  user: {turn_payload.get('user_message')}")
    print(f"  bot : {preview}")


async def _main() -> int:
    args = _parse_args()
    messages = _load_messages(args)
    session_id = args.session_id or f"cli-debug-{args.patient_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    thread_id = str(args.thread_id or "main")

    if not args.keep_memory:
        st_memory_store.clear(patient_id=args.patient_id, session_id=session_id, thread_id=thread_id)

    turns: list[dict[str, Any]] = []
    supervisor_state: dict[str, Any] | None = None

    async with async_session_factory() as session:
        patient = await researcher_crud.get_patient_by_id(session, args.patient_id)
        if patient is None:
            raise SystemExit(f"Patient not found: {args.patient_id}")

        for index, message in enumerate(messages, start=1):
            turn_result = await _run_turn(
                db=session,
                patient_id=args.patient_id,
                message=message,
                tier=args.tier,
                session_id=session_id,
                thread_id=thread_id,
                supervisor_state=supervisor_state,
                persist_messages=bool(args.persist_messages),
            )
            turn_payload = {
                "turn_number": index,
                "user_message": message,
                "assistant_reply": turn_result.response,
                "request_type": turn_result.request_type,
                "requested_model_tier": turn_result.requested_model_tier,
                "actual_model_tier": turn_result.actual_model_tier,
                "account_id": turn_result.account_id,
                "session_id": session_id,
                "thread_id": thread_id,
                "saved_to_chat": bool(args.persist_messages and turn_result.ok),
                "diagnostics_json": turn_result.diagnostics_json,
                "human_trace": turn_result.human_trace,
                "memory_before": turn_result.memory_before,
                "memory_after": turn_result.memory_after,
                "pending_st_memory": turn_result.pending_st_memory,
                "pending_lt_memory": turn_result.pending_lt_memory,
                "state_before": supervisor_state or {},
                "state_after": turn_result.supervisor_state or supervisor_state or {},
                "supervisor_state": turn_result.supervisor_state,
                "supervisor_state_delta": turn_result.supervisor_state_delta,
            }
            turns.append(turn_payload)
            _print_turn_summary(index, turn_payload)

            if turn_result.supervisor_state is not None:
                supervisor_state = dict(turn_result.supervisor_state)

            if not turn_result.ok and not args.continue_on_error:
                break

        report_payload = {
            "saved_at": datetime.now().isoformat(),
            "saved_from": "scripts.run_researcher_debug",
            "session_id": session_id,
            "thread_id": thread_id,
            "patient_id": args.patient_id,
            "patient_label": _patient_label(patient),
            "export_scope": "all",
            "turns": turns,
            "current_supervisor_state": supervisor_state or {},
        }

    target_path = _next_debug_report_path()
    target_path.write_text(_build_debug_report_markdown(report_payload), encoding="utf-8")
    print(f"\nReport saved to: {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
