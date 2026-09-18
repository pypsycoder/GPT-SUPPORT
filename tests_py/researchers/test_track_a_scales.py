"""Фаза 5 Track A — scale_item_responses.

save_scale_result пишет ответы по вопросам параллельно с answers_json
(scales.models.ScaleItemResponse), не меняя существующий контракт ScaleResult.
sqlite in-memory — FK снимаются (tests_py.sqlite_schema.create_tables), реальный
Postgres не нужен для этого юнита.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.scales.models import ScaleItemResponse, ScaleResult
from app.scales.services import save_scale_result
from tests_py.sqlite_schema import create_tables


@asynccontextmanager
async def _session_ctx():
    # save_scale_result() делает верификационный SELECT сырым SQL с
    # захардкоженным "scales.scale_results" (см. app/scales/services.py) —
    # schema_translate_map его не перепишет (работает только для ORM-статементов).
    # Поэтому вместо схема->None прикрепляем настоящую sqlite-базу "scales".
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS scales"))
        await conn.run_sync(create_tables, ScaleResult, ScaleItemResponse)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def test_save_scale_result_writes_item_responses_alongside_answers_json():
    async def runner():
        async with _session_ctx() as session:
            answers_log = [
                {"question_id": "q1", "option_id": "2", "score_value": 2},
                {"question_id": "q2", "option_id": "0", "score_value": 0},
            ]
            saved = await save_scale_result(
                session=session,
                user_id=42,
                scale_code="HADS",
                scale_version="1.0",
                result_json={"total_score": 2},
                answers_log=answers_log,
            )

            # answers_json — контракт не тронут
            assert saved.answers_json == answers_log

            rows = (
                await session.execute(
                    select(ScaleItemResponse).order_by(ScaleItemResponse.question_id)
                )
            ).scalars().all()
            assert len(rows) == 2
            assert [r.question_id for r in rows] == ["q1", "q2"]
            assert [r.answer_value for r in rows] == ["2", "0"]
            assert all(r.user_id == 42 for r in rows)
            assert all(r.result_id == saved.id for r in rows)
            assert all(r.scale_code == "HADS" for r in rows)
            assert all(r.measured_at == saved.measured_at for r in rows)

    asyncio.run(runner())


def test_save_scale_result_handles_value_style_answers_like_psqi():
    """PSQI-калькулятор кладёт в answers_log {"question_id","value"} — не option_id."""

    async def runner():
        async with _session_ctx() as session:
            answers_log = [
                {"question_id": "q1", "value": "23:30"},
                {"question_id": "q4", "value": 7},
            ]
            saved = await save_scale_result(
                session=session,
                user_id=7,
                scale_code="PSQI",
                scale_version="1.0",
                result_json={"total_score": 3},
                answers_log=answers_log,
            )

            rows = (
                await session.execute(
                    select(ScaleItemResponse)
                    .where(ScaleItemResponse.result_id == saved.id)
                    .order_by(ScaleItemResponse.question_id)
                )
            ).scalars().all()
            assert [r.answer_value for r in rows] == ["23:30", "7"]

    asyncio.run(runner())


def test_save_scale_result_skips_entries_without_question_id():
    async def runner():
        async with _session_ctx() as session:
            answers_log = [
                {"question_id": "q1", "option_id": "1"},
                {"value": "orphan, no question_id"},
            ]
            saved = await save_scale_result(
                session=session,
                user_id=1,
                scale_code="PSS10",
                scale_version="1.0",
                result_json={"total_score": 1},
                answers_log=answers_log,
            )

            rows = (
                await session.execute(
                    select(ScaleItemResponse).where(ScaleItemResponse.result_id == saved.id)
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].question_id == "q1"

    asyncio.run(runner())
