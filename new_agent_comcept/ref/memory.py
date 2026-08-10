"""
Четырёхслойная память агента + gate записи в долгосрочную.

Слои и их роль в промпте:

    working   — последние N ходов дословно. Хвост messages.
    episodic  — свёртка вытесненных ходов. Один абзац в стабильной части.
    semantic  — устойчивые факты о пациенте (key-value). Стабильная часть.
    retrieval — куски контента из pgvector/BM25. Волатильная часть, каждый ход новая.

Почему именно так, а не «складываем всю историю»:
  1. История растёт линейно, стоимость — тоже. Свёртка держит O(1).
  2. Стабильная часть должна быть стабильной: факты меняются раз в сутки,
     RAG — каждый ход. Их нельзя класть рядом, иначе RAG сбивает кэш профиля.

Ключевое правило записи в semantic:
    специалисты НЕ пишут память. Они только ПРЕДЛАГАЮТ кандидатов.
    Решение принимает gate по явным политикам. Иначе долгосрочная память
    за неделю зарастает шумом, и никакой промпт это уже не лечит.

Зависимости: pydantic, asyncpg (или любой async-драйвер — SQL вынесен в строки).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol, Sequence

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Контракты
# --------------------------------------------------------------------------- #

FactPolicy = Literal[
    "explicit_user_preference",   # пациент прямо сказал: «пиши короче»
    "repeated_pattern",           # ≥2 подтверждения в разных сессиях
    "progress_event",             # объективное событие: урок пройден, шкала заполнена
    "stable_behavior_signal",     # ≥3 однотипных выбора
]

# Минимум подтверждений для записи. Без этого LT зарастает.
POLICY_MIN_EVIDENCE: dict[str, int] = {
    "explicit_user_preference": 1,
    "progress_event": 1,
    "repeated_pattern": 2,
    "stable_behavior_signal": 3,
}

# Белый список ключей. Модель не изобретает ключи — она выбирает из enum.
# Это единственный надёжный способ не получить 400 разных написаний одного факта.
# Literal обязан быть литералом: он уезжает в JSON Schema как "enum",
# и GigaChat в strict-режиме физически не сможет вернуть ключ вне списка.
FactKey = Literal[
    "response_style_preference",
    "content_preference",
    "support_mode_preference",
    "repeated_problem_pattern",
    "stable_progress_fact",
    "current_life_circumstance",
]

# TTL по типам ключей. Всё, что про «сейчас», обязано протухать.
FACT_TTL: dict[str, timedelta | None] = {
    "response_style_preference": None,          # бессрочно
    "content_preference": None,
    "support_mode_preference": None,
    "repeated_problem_pattern": timedelta(days=90),
    "stable_progress_fact": None,
    "current_life_circumstance": timedelta(days=30),
}

ALLOWED_FACT_KEYS: tuple[str, ...] = tuple(FACT_TTL.keys())


class FactCandidate(BaseModel):
    """Кандидат в долгосрочную память. Производится агентом, но не записывается им."""

    key: FactKey
    value: str = Field(max_length=200, description="Нормализованное значение, snake_case")
    policy: FactPolicy
    evidence: str = Field(max_length=300, description="Цитата пациента или описание события")
    confidence: float = Field(ge=0.0, le=1.0)


class MemoryDecision(BaseModel):
    key: str
    written: bool
    reason: str


@dataclass(slots=True)
class Fact:
    key: str
    value: Any
    policy: str
    confidence: float
    evidence_count: int
    updated_at: datetime


@dataclass(slots=True)
class WorkingWindow:
    turns: list[dict[str, Any]]
    last_seq: int


# --------------------------------------------------------------------------- #
# Абстракция БД: подставьте свой пул
# --------------------------------------------------------------------------- #

class DB(Protocol):
    async def fetch(self, sql: str, *args: Any) -> Sequence[Any]: ...
    async def fetchrow(self, sql: str, *args: Any) -> Any: ...
    async def execute(self, sql: str, *args: Any) -> Any: ...


# --------------------------------------------------------------------------- #
# Репозиторий памяти
# --------------------------------------------------------------------------- #

class MemoryStore:
    def __init__(self, db: DB) -> None:
        self.db = db

    # ------------------------------ working ---------------------------------

    async def append_turn(
        self,
        thread_id: str,
        role: str,
        content: str,
        *,
        tokens: int = 0,
        function_call: dict[str, Any] | None = None,
        functions_state_id: str | None = None,
    ) -> int:
        row = await self.db.fetchrow(
            """
            INSERT INTO agent.turn
                (thread_id, seq, role, content, tokens, function_call, functions_state_id)
            VALUES (
                $1,
                COALESCE((SELECT max(seq) FROM agent.turn WHERE thread_id = $1), 0) + 1,
                $2, $3, $4, $5, $6
            )
            RETURNING seq
            """,
            thread_id, role, content, tokens,
            json.dumps(function_call) if function_call else None,
            functions_state_id,
        )
        return int(row["seq"])

    async def read_window(self, thread_id: str, *, limit: int = 12) -> WorkingWindow:
        rows = await self.db.fetch(
            """
            SELECT seq, role, content, functions_state_id, function_call
            FROM agent.turn
            WHERE thread_id = $1 AND compacted = FALSE
            ORDER BY seq DESC
            LIMIT $2
            """,
            thread_id, limit,
        )
        turns = [dict(r) for r in reversed(list(rows))]
        return WorkingWindow(turns=turns, last_seq=turns[-1]["seq"] if turns else 0)

    async def mark_compacted(self, thread_id: str, seq_to: int) -> None:
        await self.db.execute(
            "UPDATE agent.turn SET compacted = TRUE WHERE thread_id = $1 AND seq <= $2",
            thread_id, seq_to,
        )

    # ------------------------------ episodic --------------------------------

    async def latest_summary(self, thread_id: str) -> tuple[str, int]:
        row = await self.db.fetchrow(
            "SELECT text, seq_to FROM agent.summary WHERE thread_id=$1 ORDER BY seq_to DESC LIMIT 1",
            thread_id,
        )
        return (row["text"], int(row["seq_to"])) if row else ("", 0)

    async def save_summary(
        self, thread_id: str, text: str, seq_from: int, seq_to: int, *, version: str = "v1"
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO agent.summary (thread_id, seq_from, seq_to, text, tokens, summarizer_version)
            VALUES ($1,$2,$3,$4,$5,$6)
            """,
            thread_id, seq_from, seq_to, text, max(1, len(text) // 4), version,
        )

    # ------------------------------ semantic --------------------------------

    async def read_facts(self, patient_id: int) -> list[Fact]:
        rows = await self.db.fetch(
            """
            SELECT key, value, policy, confidence, evidence_count, updated_at
            FROM agent.fact
            WHERE patient_id = $1
              AND status = 'active'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY key
            """,
            patient_id,
        )
        return [
            Fact(
                key=r["key"],
                value=r["value"],
                policy=r["policy"],
                confidence=float(r["confidence"]),
                evidence_count=int(r["evidence_count"]),
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    async def _upsert_fact(self, patient_id: int, cand: FactCandidate) -> None:
        """
        UPSERT с накоплением подтверждений.

        Если значение то же — растим evidence_count и confidence.
        Если другое — старый факт помечается superseded, пишется новый.
        Логика «затираем молча» — источник самых неприятных багов памяти.
        """
        existing = await self.db.fetchrow(
            "SELECT id, value, evidence_count, evidence FROM agent.fact "
            "WHERE patient_id=$1 AND key=$2 AND status='active'",
            patient_id, cand.key,
        )
        ttl = FACT_TTL.get(cand.key)
        expires_at = datetime.now(UTC) + ttl if ttl else None
        new_value = json.dumps(cand.value, ensure_ascii=False)

        if existing and json.loads(existing["value"]) == cand.value:
            await self.db.execute(
                """
                UPDATE agent.fact
                SET evidence_count = evidence_count + 1,
                    confidence = LEAST(0.99, confidence + 0.1),
                    evidence = (evidence || $2::jsonb),
                    expires_at = $3,
                    updated_at = now()
                WHERE id = $1
                """,
                existing["id"],
                json.dumps([cand.evidence], ensure_ascii=False),
                expires_at,
            )
            return

        if existing:
            await self.db.execute(
                "UPDATE agent.fact SET status='superseded', updated_at=now() WHERE id=$1",
                existing["id"],
            )
            await self.db.execute(
                """
                INSERT INTO agent.fact_history (fact_id, patient_id, key, old_value, new_value, reason)
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                existing["id"], patient_id, cand.key,
                existing["value"], new_value, f"superseded_by:{cand.policy}",
            )

        await self.db.execute(
            """
            INSERT INTO agent.fact
                (patient_id, key, value, policy, confidence, evidence_count, evidence, expires_at)
            VALUES ($1,$2,$3::jsonb,$4,$5,1,$6::jsonb,$7)
            """,
            patient_id, cand.key, new_value, cand.policy, cand.confidence,
            json.dumps([cand.evidence], ensure_ascii=False), expires_at,
        )

    async def count_pending_evidence(self, patient_id: int, key: str, value: str) -> int:
        """Сколько раз этот же факт уже предлагался (для политик с порогом ≥2)."""
        row = await self.db.fetchrow(
            """
            SELECT coalesce(evidence_count, 0) AS c
            FROM agent.fact
            WHERE patient_id=$1 AND key=$2 AND value = $3::jsonb AND status='active'
            """,
            patient_id, key, json.dumps(value, ensure_ascii=False),
        )
        return int(row["c"]) if row else 0


# --------------------------------------------------------------------------- #
# Memory gate — единственная точка записи в semantic
# --------------------------------------------------------------------------- #

class MemoryGate:
    """
    Детерминированный фильтр. Никаких LLM-вызовов: решение о записи в
    долгосрочную память слишком дорогое, чтобы отдавать его вероятностной модели.

    Модель предлагает кандидатов -> gate проверяет политику, порог
    подтверждений и белый список ключей -> пишет или отклоняет с причиной.
    """

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def apply(
        self, patient_id: int, candidates: Sequence[FactCandidate]
    ) -> list[MemoryDecision]:
        decisions: list[MemoryDecision] = []
        for cand in candidates:
            if cand.key not in ALLOWED_FACT_KEYS:
                decisions.append(MemoryDecision(key=cand.key, written=False, reason="key_not_allowed"))
                continue
            if cand.confidence < 0.6:
                decisions.append(MemoryDecision(key=cand.key, written=False, reason="low_confidence"))
                continue

            need = POLICY_MIN_EVIDENCE[cand.policy]
            have = await self.store.count_pending_evidence(patient_id, cand.key, cand.value)
            if have + 1 < need:
                # Записываем как накопление, но факт ещё не «боевой».
                await self.store._upsert_fact(patient_id, cand)
                decisions.append(
                    MemoryDecision(
                        key=cand.key, written=False,
                        reason=f"evidence_{have + 1}_of_{need}",
                    )
                )
                continue

            await self.store._upsert_fact(patient_id, cand)
            decisions.append(MemoryDecision(key=cand.key, written=True, reason=cand.policy))
        return decisions


# --------------------------------------------------------------------------- #
# Рендер фактов в промпт
# --------------------------------------------------------------------------- #

def render_facts(facts: Sequence[Fact]) -> str:
    """
    Компактный детерминированный рендер. Сортировка по ключу обязательна:
    иначе порядок плавает и префикс кэша ломается на ровном месте.
    """
    if not facts:
        return ""
    lines = [f"- {f.key}: {f.value}" for f in sorted(facts, key=lambda x: x.key)]
    return "\n".join(lines)
