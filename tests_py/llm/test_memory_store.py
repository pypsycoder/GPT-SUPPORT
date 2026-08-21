"""Тесты gate персистентной семантической памяти и фоновой свёртки (шаг 5).

Своя in-memory sqlite на тест вместо реальной БД — быстро и изолированно,
паттерн как в ``tests_py/researchers/test_chat_debug.py``. Postgres-специфика
(частичный уникальный индекс) отдельной sqlite-схемой не проверяется.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.llm import memory_store
from app.llm.pool import StructuredResult
from app.models.llm import ChatMessage, ChatSummary, PatientFact, PatientFactHistory
from app.users.models import User
from tests_py.sqlite_schema import create_tables


@asynccontextmanager
async def memory_session_ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, User, PatientFact, PatientFactHistory)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _make_patient(session: AsyncSession, number: int) -> User:
    patient = User(full_name=f"Patient {number}", patient_number=number)
    session.add(patient)
    await session.commit()
    await session.refresh(patient)
    return patient


def test_new_candidate_created_as_pending_not_yet_active():
    async def runner():
        async with memory_session_ctx() as session:
            patient = await _make_patient(session, 1)

            decisions = await memory_store.stage_candidates(
                session, patient_id=patient.id, candidates=["Любит утренние прогулки"]
            )
            await session.commit()

            assert len(decisions) == 1
            assert decisions[0].action == "created_pending"
            # Один кандидат ещё не факт: порог подтверждения — два упоминания.
            assert await memory_store.list_active_facts_text(session, patient.id) == []

    asyncio.run(runner())


def test_duplicate_candidate_within_same_batch_does_not_promote():
    """Регрессия code review: агент вернул один кандидат дважды в ОДНОМ ответе —
    это не "упоминание в другом ходу", факт не должен становиться активным."""

    async def runner():
        async with memory_session_ctx() as session:
            patient = await _make_patient(session, 20)

            decisions = await memory_store.stage_candidates(
                session,
                patient_id=patient.id,
                candidates=["Любит утренние прогулки", "любит   утренние прогулки!"],
            )
            await session.commit()

            assert decisions[0].action == "created_pending"
            assert decisions[1].action == "duplicate_in_batch"
            assert await memory_store.list_active_facts_text(session, patient.id) == []

            result = await session.execute(
                select(PatientFact).where(PatientFact.patient_id == patient.id)
            )
            rows = list(result.scalars().all())
            assert len(rows) == 1
            assert rows[0].evidence_count == 1
            assert rows[0].status == "pending"

    asyncio.run(runner())


def test_repeated_candidate_promotes_to_active():
    async def runner():
        async with memory_session_ctx() as session:
            patient = await _make_patient(session, 2)

            await memory_store.stage_candidates(
                session, patient_id=patient.id, candidates=["Любит утренние прогулки"]
            )
            await session.commit()

            decisions = await memory_store.stage_candidates(
                session, patient_id=patient.id, candidates=["любит   утренние прогулки!"]
            )
            await session.commit()

            assert decisions[0].action == "promoted"
            facts = await memory_store.list_active_facts_text(session, patient.id)
            assert facts == ["Любит утренние прогулки"]

    asyncio.run(runner())


def test_repeated_active_fact_refreshes_ttl_instead_of_duplicating():
    async def runner():
        async with memory_session_ctx() as session:
            patient = await _make_patient(session, 3)

            for _ in range(2):
                await memory_store.stage_candidates(
                    session, patient_id=patient.id, candidates=["Соблюдает водный режим"]
                )
                await session.commit()

            result = await session.execute(
                select(PatientFact).where(PatientFact.patient_id == patient.id)
            )
            rows = list(result.scalars().all())
            assert len(rows) == 1  # не задублировался
            assert rows[0].status == "active"
            first_expiry = rows[0].expires_at

            # Третье упоминание: TTL продлевается (sliding), а не создаётся новая строка.
            decisions = await memory_store.stage_candidates(
                session, patient_id=patient.id, candidates=["Соблюдает водный режим"]
            )
            await session.commit()
            assert decisions[0].action == "refreshed"

            result = await session.execute(
                select(PatientFact).where(PatientFact.patient_id == patient.id)
            )
            rows = list(result.scalars().all())
            assert len(rows) == 1
            assert rows[0].expires_at >= first_expiry

    asyncio.run(runner())


def test_capacity_cap_evicts_oldest_active_fact():
    async def runner():
        async with memory_session_ctx() as session:
            patient = await _make_patient(session, 4)

            for i in range(memory_store.MAX_ACTIVE_FACTS):
                text = f"Факт номер {i}"
                await memory_store.stage_candidates(session, patient_id=patient.id, candidates=[text])
                await memory_store.stage_candidates(session, patient_id=patient.id, candidates=[text])
            await session.commit()

            facts = await memory_store.list_active_facts_text(session, patient.id)
            assert len(facts) == memory_store.MAX_ACTIVE_FACTS

            # Делаем "Факт номер 0" однозначно самым старым по last_seen_at,
            # не полагаясь на разрешение системных часов между быстрыми вызовами.
            oldest = await session.execute(
                select(PatientFact).where(
                    PatientFact.patient_id == patient.id,
                    PatientFact.normalized_key == "факт номер 0",
                )
            )
            oldest_row = oldest.scalar_one()
            oldest_row.last_seen_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=10)
            await session.commit()

            await memory_store.stage_candidates(session, patient_id=patient.id, candidates=["Новый факт"])
            decisions = await memory_store.stage_candidates(
                session, patient_id=patient.id, candidates=["Новый факт"]
            )
            await session.commit()
            assert decisions[0].action == "promoted"

            facts_after = await memory_store.list_active_facts_text(session, patient.id)
            assert len(facts_after) == memory_store.MAX_ACTIVE_FACTS
            assert "Новый факт" in facts_after
            assert "Факт номер 0" not in facts_after

            history = await session.execute(
                select(PatientFactHistory).where(PatientFactHistory.reason == "capacity_evicted")
            )
            assert len(list(history.scalars().all())) == 1

    asyncio.run(runner())


def test_expired_fact_excluded_from_active_list():
    async def runner():
        async with memory_session_ctx() as session:
            patient = await _make_patient(session, 5)
            now = datetime.now(UTC).replace(tzinfo=None)
            session.add(
                PatientFact(
                    patient_id=patient.id,
                    text="Протухший факт",
                    normalized_key="протухший факт",
                    status="active",
                    evidence_count=2,
                    first_seen_at=now - timedelta(days=60),
                    last_seen_at=now - timedelta(days=46),
                    expires_at=now - timedelta(days=1),
                )
            )
            await session.commit()

            assert await memory_store.list_active_facts_text(session, patient.id) == []

    asyncio.run(runner())


def test_empty_candidate_is_ignored():
    async def runner():
        async with memory_session_ctx() as session:
            patient = await _make_patient(session, 6)

            decisions = await memory_store.stage_candidates(
                session, patient_id=patient.id, candidates=["   ", "..."]
            )
            await session.commit()

            assert all(d.action == "ignored_empty" for d in decisions)
            assert await memory_store.list_active_facts_text(session, patient.id) == []

    asyncio.run(runner())


def test_normalize_candidate_dedups_on_whitespace_case_and_punctuation():
    clean_a, key_a = memory_store.normalize_candidate("  Любит   утренние прогулки!! ")
    clean_b, key_b = memory_store.normalize_candidate("любит утренние прогулки")
    assert key_a == key_b
    assert clean_a == "Любит утренние прогулки!!"


# --------------------------------------------------------------------------- #
# maybe_compact — фоновая свёртка вытесненных из окна ходов
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def compaction_session_ctx():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, User, ChatMessage, ChatSummary)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


def test_maybe_compact_summarizes_evicted_turns_and_advances_cursor(monkeypatch):
    async def runner():
        async with compaction_session_ctx() as session_factory:
            async with session_factory() as session:
                patient = User(full_name="Compaction Patient", patient_number=7)
                session.add(patient)
                await session.commit()
                await session.refresh(patient)

                # 3 пары user/assistant: с window_turns=2 вытеснится первая пара
                # целиком плюс первое сообщение второй пары (4 хода из 6).
                for i in range(3):
                    session.add(
                        ChatMessage(
                            patient_id=patient.id,
                            thread_id="default",
                            role="user",
                            content=f"Сообщение пациента {i}",
                        )
                    )
                    session.add(
                        ChatMessage(
                            patient_id=patient.id,
                            thread_id="default",
                            role="assistant",
                            content=f"Ответ ассистента {i}",
                        )
                    )
                await session.commit()

                result = await session.execute(
                    select(ChatMessage).order_by(ChatMessage.id.asc())
                )
                all_messages = list(result.scalars().all())
                expected_cutoff_id = all_messages[3].id  # 4-й ход (assistant1)

            fake_client = SimpleNamespace(
                structured=AsyncMock(
                    return_value=StructuredResult(
                        parsed=SimpleNamespace(digest="Пациент рассказывал о самочувствии."),
                        raw_text="",
                    )
                )
            )
            fake_pool = SimpleNamespace(get_available=AsyncMock(return_value=fake_client))
            monkeypatch.setattr("app.llm.pool.pool", fake_pool)
            monkeypatch.setattr("core.db.engine.async_session_maker", session_factory)

            await memory_store.maybe_compact(
                patient.id, "default", window_turns=2, window_chars=6000
            )

            async with session_factory() as session:
                digest = await memory_store.get_digest(
                    session, patient_id=patient.id, thread_id="default"
                )
                assert digest == "Пациент рассказывал о самочувствии."

                summary = (
                    await session.execute(
                        select(ChatSummary).where(ChatSummary.patient_id == patient.id)
                    )
                ).scalar_one()
                assert summary.covered_through_message_id == expected_cutoff_id

    asyncio.run(runner())


def test_maybe_compact_is_noop_when_nothing_evicted(monkeypatch):
    async def runner():
        async with compaction_session_ctx() as session_factory:
            async with session_factory() as session:
                patient = User(full_name="No Compaction Patient", patient_number=8)
                session.add(patient)
                await session.commit()
                await session.refresh(patient)

                session.add(
                    ChatMessage(patient_id=patient.id, thread_id="default", role="user", content="Привет")
                )
                session.add(
                    ChatMessage(patient_id=patient.id, thread_id="default", role="assistant", content="Привет!")
                )
                await session.commit()

            fake_pool = SimpleNamespace(get_available=AsyncMock())
            monkeypatch.setattr("app.llm.pool.pool", fake_pool)
            monkeypatch.setattr("core.db.engine.async_session_maker", session_factory)

            # Всего 2 хода, window_turns=12 — вытеснять нечего, LLM не вызывается.
            await memory_store.maybe_compact(patient.id, "default")

            fake_pool.get_available.assert_not_called()
            async with session_factory() as session:
                digest = await memory_store.get_digest(
                    session, patient_id=patient.id, thread_id="default"
                )
                assert digest == ""

    asyncio.run(runner())


def test_maybe_compact_never_raises_on_llm_failure(monkeypatch):
    async def runner():
        async with compaction_session_ctx() as session_factory:
            async with session_factory() as session:
                patient = User(full_name="Failing Compaction Patient", patient_number=9)
                session.add(patient)
                await session.commit()
                await session.refresh(patient)

                for i in range(3):
                    session.add(
                        ChatMessage(patient_id=patient.id, thread_id="default", role="user", content=f"У {i}")
                    )
                    session.add(
                        ChatMessage(patient_id=patient.id, thread_id="default", role="assistant", content=f"А {i}")
                    )
                await session.commit()

            fake_client = SimpleNamespace(
                structured=AsyncMock(side_effect=memory_store.LLMError("boom"))
            )
            fake_pool = SimpleNamespace(get_available=AsyncMock(return_value=fake_client))
            monkeypatch.setattr("app.llm.pool.pool", fake_pool)
            monkeypatch.setattr("core.db.engine.async_session_maker", session_factory)

            # Не должно бросить исключение наружу — фон вне критического пути.
            await memory_store.maybe_compact(patient.id, "default", window_turns=2, window_chars=6000)

    asyncio.run(runner())
