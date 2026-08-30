"""
Персистентная память проекта (см. pipeline/STRUCTURE.md, «Память»).

Working-память (сырой лог ходов) уже персистентна в ``llm.chat_messages``, а
состояние хода (goal/slots/техника) — в ``llm.chat_supervisor_states``. Здесь
закрываются два оставшихся слоя памяти (см. pipeline/STRUCTURE.md, «Память»):

  * семантическая  — устойчивые факты о пациенте (``llm.patient_facts``);
  * эпизодическая  — свёртка ходов, вытесненных из окна диалога (``llm.chat_summaries``).

Решение о записи факта принимает детерминированный код этого модуля, а не
модель: ``AgentReply.memory_candidates`` — произвольный текст без key/value
(схема отдаёт ``list[str]`` намеренно, см. ``app.llm.agent.schemas`` — поля
там дорогие и хрупкие). Поэтому идентичность факта здесь определяется
совпадением нормализованного текста между ходами, а не ключом от модели.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.errors import LLMError
from app.llm.prompt_assembly import DEFAULT_WINDOW_CHARS, DEFAULT_WINDOW_TURNS
from app.llm.structured import JSON_ONLY_INSTRUCTION
from app.models.llm import ChatMessage, ChatSummary, PatientFact, PatientFactHistory

logger = logging.getLogger("gpt-support-llm.memory_store")

# Факт, не подтверждённый повторно, живёт максимум 45 дней с последнего
# упоминания (sliding TTL) — протухшие описания «сейчас» не должны ехать в
# промпт бесконечно (см. pipeline/STRUCTURE.md, «Память»).
FACT_TTL_DAYS = 45

# Потолок активных фактов на пациента: без него профиль пациента через
# месяцы бесконтрольной записи превращается в шум (см. pipeline/STRUCTURE.md, «Память»).
MAX_ACTIVE_FACTS = 20

# Порог подтверждений: кандидат становится активным фактом только когда
# упомянут во второй раз в другом ходу — одно упоминание слишком шумно.
PROMOTION_MIN_EVIDENCE = 2

MAX_CANDIDATE_LEN = 200
MAX_DIGEST_CHARS = 1200

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_candidate(text: str) -> tuple[str, str]:
    """Возвращает (обрезанный исходный текст, нормализованный ключ для дедупа)."""
    clean = _WS_RE.sub(" ", str(text or "")).strip()[:MAX_CANDIDATE_LEN]
    key = _PUNCT_RE.sub("", clean.lower())
    key = _WS_RE.sub(" ", key).strip()
    return clean, key


@dataclass(slots=True)
class FactDecision:
    text: str
    normalized_key: str
    action: str  # created_pending | promoted | refreshed | ignored_empty
    fact_id: int | None = None


async def stage_candidates(
    db: AsyncSession,
    *,
    patient_id: int,
    candidates: list[str],
) -> list[FactDecision]:
    """Прогоняет кандидатов от агента через gate. Добавляет объекты в сессию,
    но НЕ коммитит — коммит остаётся в роутере (CLAUDE.md).
    """
    decisions: list[FactDecision] = []
    if not candidates:
        return decisions

    result = await db.execute(
        select(PatientFact).where(
            PatientFact.patient_id == patient_id,
            PatientFact.status.in_(("pending", "active")),
        )
    )
    existing = {row.normalized_key: row for row in result.scalars().all()}

    now = datetime.now(UTC).replace(tzinfo=None)
    expires_at = now + timedelta(days=FACT_TTL_DAYS)

    # Кандидат может повториться дважды в одном ответе агента (схема этого не
    # запрещает) — такой повтор не считается "упоминанием в другом ходу" и не
    # должен продвигать evidence_count, иначе факт продвигается за один ход
    # вместо двух, а строка ещё не flush-нута (row.id is None → fact_id=0 в истории).
    seen_in_batch: set[str] = set()

    for raw in candidates:
        clean, key = normalize_candidate(raw)
        if not key:
            decisions.append(FactDecision(text=clean, normalized_key=key, action="ignored_empty"))
            continue

        if key in seen_in_batch:
            decisions.append(FactDecision(text=clean, normalized_key=key, action="duplicate_in_batch"))
            continue
        seen_in_batch.add(key)

        row = existing.get(key)
        if row is None:
            row = PatientFact(
                patient_id=patient_id,
                text=clean,
                normalized_key=key,
                status="pending",
                evidence_count=1,
                first_seen_at=now,
                last_seen_at=now,
                expires_at=expires_at,
            )
            db.add(row)
            existing[key] = row
            decisions.append(FactDecision(text=clean, normalized_key=key, action="created_pending"))
            continue

        row.evidence_count += 1
        row.last_seen_at = now
        row.expires_at = expires_at

        if row.status == "pending" and row.evidence_count >= PROMOTION_MIN_EVIDENCE:
            row.status = "active"
            db.add(
                PatientFactHistory(
                    fact_id=row.id or 0,
                    patient_id=patient_id,
                    old_status="pending",
                    new_status="active",
                    reason="promoted",
                )
            )
            await _enforce_capacity(db, patient_id=patient_id, keep_key=key, now=now)
            decisions.append(FactDecision(text=clean, normalized_key=key, action="promoted", fact_id=row.id))
        else:
            decisions.append(FactDecision(text=clean, normalized_key=key, action="refreshed", fact_id=row.id))

    return decisions


async def _enforce_capacity(
    db: AsyncSession,
    *,
    patient_id: int,
    keep_key: str,
    now: datetime,
) -> None:
    """Вытесняет самый старый активный факт сверх потолка ``MAX_ACTIVE_FACTS``."""
    result = await db.execute(
        select(PatientFact)
        .where(PatientFact.patient_id == patient_id, PatientFact.status == "active")
        .order_by(PatientFact.last_seen_at.asc())
    )
    active = list(result.scalars().all())
    overflow = len(active) - MAX_ACTIVE_FACTS
    if overflow <= 0:
        return

    for row in active:
        if overflow <= 0:
            break
        if row.normalized_key == keep_key:
            continue
        row.status = "superseded"
        db.add(
            PatientFactHistory(
                fact_id=row.id or 0,
                patient_id=patient_id,
                old_status="active",
                new_status="superseded",
                reason="capacity_evicted",
            )
        )
        overflow -= 1


async def list_active_facts_text(db: AsyncSession, patient_id: int) -> list[str]:
    """Активные и не протухшие факты — для профильного слоя [1] промпта."""
    now = datetime.now(UTC).replace(tzinfo=None)
    result = await db.execute(
        select(PatientFact.text)
        .where(
            PatientFact.patient_id == patient_id,
            PatientFact.status == "active",
        )
        .where((PatientFact.expires_at.is_(None)) | (PatientFact.expires_at > now))
        .order_by(PatientFact.last_seen_at.desc())
    )
    return [str(text) for text in result.scalars().all()]


# --------------------------------------------------------------------------- #
# Эпизодическая память: свёртка вытесненных из окна ходов
# --------------------------------------------------------------------------- #

class _DigestUpdate(BaseModel):
    """Однополевая схема для structured() — Lite-модель обновляет свёртку."""

    model_config = ConfigDict(extra="ignore")

    digest: str = Field(max_length=MAX_DIGEST_CHARS, description="Обновлённая краткая свёртка беседы")


_SUMMARIZER_SYSTEM_PROMPT = (
    "Ты сжимаешь историю переписки пациента на диализе с ассистентом поддержки "
    "в короткую свёртку на русском языке, не длиннее нескольких предложений. "
    "Сохраняй устойчивые темы, договорённости и эмоциональный контекст. "
    "Не придумывай факты, которых не было в переписке. Не используй markdown.\n\n"
    # Единственный вызывающий этот промпт путь работает на pool.get_available("lite")
    # и раньше не включал эту инструкцию — единственный structured()-вызов в
    # проекте без неё. Живым прогоном (16-ходовый тред, cross-cutting проверка
    # свёртки истории) поймано: без инструкции Lite на длинной истории
    # придумывает СВОЮ JSON-схему (topics/agreements/emotional_context/...)
    # вместо однополевой {"digest": "..."} — обе попытки structured() падают,
    # maybe_compact молча возвращается без записи (см. её except LLMError),
    # и chat_summaries вообще не создаётся. Тот же класс сбоя и то же лекарство,
    # что уже задокументированы в router_l2.py.
    f'{JSON_ONLY_INSTRUCTION} Схема: {{"digest": "..."}}.'
)


def _format_turns_for_digest(turns: list[ChatMessage]) -> str:
    lines = [f"{'Пациент' if t.role == 'user' else 'Ассистент'}: {t.content}" for t in turns]
    return "\n".join(lines)


async def get_digest(db: AsyncSession, *, patient_id: int, thread_id: str) -> str:
    """Сохранённая свёртка для слоя [2] промпта."""
    result = await db.execute(
        select(ChatSummary.digest).where(
            ChatSummary.patient_id == patient_id,
            ChatSummary.thread_id == thread_id,
        )
    )
    row = result.first()
    return str(row[0]) if row and row[0] else ""


async def maybe_compact(
    patient_id: int,
    thread_id: str,
    *,
    window_turns: int = DEFAULT_WINDOW_TURNS,
    window_chars: int = DEFAULT_WINDOW_CHARS,
) -> None:
    """Фоновая свёртка: вне критического пути запроса, ошибки не пробрасываются.

    Открывает свою сессию (паттерн ``app/llm/scheduler.py``), т.к. вызывается
    из ``BackgroundTasks`` уже после того, как сессия запроса могла закрыться.
    """
    from app.llm import prompt_assembly
    from app.llm.pool import pool
    from core.db.engine import async_session_maker

    started = time.monotonic()
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.patient_id == patient_id, ChatMessage.thread_id == thread_id)
                .order_by(ChatMessage.id.asc())
            )
            messages = list(result.scalars().all())
            if not messages:
                return

            # Строятся одним проходом, чтобы `filtered[i]` и `turns[i]`
            # гарантированно указывали на один и тот же ход — trim_window()
            # работает только с Turn и не знает про message.id.
            filtered: list[ChatMessage] = []
            turns: list[prompt_assembly.Turn] = []
            for m in messages:
                if m.role not in ("user", "assistant") or not str(m.content or "").strip():
                    continue
                filtered.append(m)
                turns.append(prompt_assembly.Turn(role=m.role, content=m.content))  # type: ignore[arg-type]
            if not filtered:
                return

            _kept, evicted = prompt_assembly.trim_window(
                turns, max_turns=window_turns, max_chars=window_chars
            )
            if not evicted:
                return

            summary_result = await db.execute(
                select(ChatSummary).where(
                    ChatSummary.patient_id == patient_id, ChatSummary.thread_id == thread_id
                )
            )
            summary_row = summary_result.scalar_one_or_none()
            covered_through = summary_row.covered_through_message_id if summary_row else 0

            # `evicted` — префикс `turns` (trim_window обрезает только с головы),
            # поэтому последнее вытесненное сообщение — `filtered[len(evicted) - 1]`.
            new_cutoff_id = filtered[len(evicted) - 1].id
            if new_cutoff_id <= covered_through:
                return

            previous_digest = summary_row.digest if summary_row else ""
            evicted_text = _format_turns_for_digest(
                [m for m in filtered if m.id > covered_through and m.id <= new_cutoff_id]
            )
            if not evicted_text.strip():
                return

            prompt = (
                (f"Текущая свёртка:\n{previous_digest}\n\n" if previous_digest else "")
                + f"Новые ходы для добавления в свёртку:\n{evicted_text}"
            )

            try:
                client = await pool.get_available("lite")
                run = await client.structured(
                    [{"role": "user", "content": prompt}],
                    _SUMMARIZER_SYSTEM_PROMPT,
                    _DigestUpdate,
                    step="summarizer",
                    patient_id=patient_id,
                    # Общий session_id: системный промпт суммаризатора константный,
                    # а пользовательская часть (свёртка + вытесненные ходы) каждый
                    # раз новая — кэшируется только префикс. Без X-Session-ID сервер
                    # клал этот вызов мимо кэша (`session_key IS NULL`, ~430 тыс.
                    # prompt-токенов за 14 дней). Тот же приём, что и в judge.
                    session_id="summarizer-shared",
                )
            except LLMError as exc:
                logger.warning(
                    "[memory_store] compaction LLM call failed patient=%d thread=%s: %s",
                    patient_id, thread_id, exc,
                )
                return

            digest_text = run.parsed.digest.strip()[:MAX_DIGEST_CHARS]
            if not digest_text:
                return

            if summary_row is None:
                summary_row = ChatSummary(
                    patient_id=patient_id,
                    thread_id=thread_id,
                    digest=digest_text,
                    covered_through_message_id=new_cutoff_id,
                )
                db.add(summary_row)
            else:
                summary_row.digest = digest_text
                summary_row.covered_through_message_id = new_cutoff_id

            await db.commit()
            logger.info(
                "[memory_store] compacted patient=%d thread=%s through=%d latency_ms=%d",
                patient_id, thread_id, new_cutoff_id, int((time.monotonic() - started) * 1000),
            )
    except Exception:  # noqa: BLE001 — фон: ничего не должно уронить основной поток
        logger.exception("[memory_store] compaction failed patient=%d thread=%s", patient_id, thread_id)
