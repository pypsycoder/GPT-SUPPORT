"""Координатор проактива: ранжирование, дедуп, потолок, сбор, доставка."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.llm import proactive_coordinator as pc
from app.models.llm import ChatMessage, ProactiveDelivery
from tests_py.sqlite_schema import create_tables


# kind → request_type, как проставляют реальные генераторы
_RT = {"misses": "morning", "praise": "morning", "idle": "motivator",
       "crisis": "safety", "anomaly": "proactive", "domain": "proactive"}


def _cand(kind: str, key: str, *, domain=None, text="…", llm=None) -> pc.ProactiveCandidate:
    return pc.ProactiveCandidate(
        kind=kind, dedup_key=key, trigger_reason="t", domain=domain,
        text=None if llm else text, llm_prompt=llm, request_type=_RT.get(kind, "proactive"),
    )


# --------------------------------------------------------------------------- #
# select_candidates — чистая логика
# --------------------------------------------------------------------------- #

def test_orders_by_priority_crisis_first():
    picked = pc.select_candidates(
        [_cand("praise", "morning"), _cand("crisis", "anomaly:systolic_bp", domain="vitals"),
         _cand("idle", "idle:sleep", domain="sleep")],
        already_sent_keys=set(), cap=3,
    )
    assert [c.kind for c in picked] == ["crisis", "idle", "praise"]


def test_respects_daily_cap():
    picked = pc.select_candidates(
        [_cand("misses", "morning"), _cand("idle", "idle:sleep", domain="sleep"),
         _cand("praise", "streak")],
        already_sent_keys=set(), cap=2,
    )
    assert len(picked) == 2
    assert [c.dedup_key for c in picked] == ["morning", "idle:sleep"]


def test_crisis_bypasses_cap():
    picked = pc.select_candidates(
        [_cand("misses", "morning"), _cand("idle", "idle:sleep", domain="sleep"),
         _cand("crisis", "anomaly:systolic_bp", domain="vitals")],
        already_sent_keys=set(), cap=1,
    )
    assert "anomaly:systolic_bp" in {c.dedup_key for c in picked}
    assert len(picked) == 2  # cap=1 обычных + кризис сверху


def test_skips_keys_already_sent_today():
    picked = pc.select_candidates(
        [_cand("misses", "morning"), _cand("idle", "idle:sleep", domain="sleep")],
        already_sent_keys={"morning"}, cap=3,
    )
    assert [c.dedup_key for c in picked] == ["idle:sleep"]


def test_one_candidate_per_domain():
    # аномалия и доменный нудж оба про vitals — берём только аномалию (важнее)
    picked = pc.select_candidates(
        [_cand("domain", "domain:vitals", domain="vitals"),
         _cand("anomaly", "anomaly:systolic_bp", domain="vitals")],
        already_sent_keys=set(), cap=3,
    )
    assert [c.dedup_key for c in picked] == ["anomaly:systolic_bp"]


def test_nothing_selected_when_all_sent():
    assert pc.select_candidates(
        [_cand("misses", "morning")], already_sent_keys={"morning"}, cap=3,
    ) == []


def test_allow_llm_false_drops_generation_candidates():
    picked = pc.select_candidates(
        [_cand("misses", "morning"), _cand("domain", "domain:sleep", domain="sleep", llm="prompt")],
        already_sent_keys=set(), cap=3, allow_llm=False,
    )
    assert [c.dedup_key for c in picked] == ["morning"]


def test_allow_llm_false_keeps_template_crisis():
    # кризисная аномалия — шаблон, не генерация; доходит и на login
    picked = pc.select_candidates(
        [_cand("crisis", "anomaly:systolic_bp", domain="vitals", text="давление 200")],
        already_sent_keys=set(), cap=1, allow_llm=False,
    )
    assert [c.dedup_key for c in picked] == ["anomaly:systolic_bp"]


# --------------------------------------------------------------------------- #
# collect_candidates — генераторы замоканы
# --------------------------------------------------------------------------- #

def _patch_collect_sources(monkeypatch, *, anom=None, morning=None, motiv=None, domain=None, has_data=True):
    async def _anom(pid, db):
        return list(anom or [])

    async def _morning(pid, db):
        if isinstance(morning, Exception):
            raise morning
        return list(morning or [])

    async def _motiv(pid, db):
        return list(motiv or [])

    async def _domain(pid, db):
        return list(domain or [])

    async def _has_data(pid, db):
        return has_data

    monkeypatch.setattr(pc, "_anomaly_candidates", _anom)
    monkeypatch.setattr(pc, "_morning_candidate", _morning)
    monkeypatch.setattr(pc, "_motivator_candidate", _motiv)
    monkeypatch.setattr(pc, "_domain_score_candidates", _domain)
    monkeypatch.setattr("app.llm.domain_scorer.has_tracked_data", _has_data)


def test_collect_merges_sources_and_survives_a_failure(monkeypatch):
    _patch_collect_sources(
        monkeypatch,
        anom=[_cand("anomaly", "anomaly:pulse", domain="vitals")],
        morning=ValueError("build_daily_context boom"),
        motiv=[_cand("idle", "idle:sleep", domain="sleep")],
    )

    got = asyncio.run(pc.collect_candidates(1, db=object(), trigger="login"))

    assert {c.dedup_key for c in got} == {"anomaly:pulse", "idle:sleep"}


def test_collect_cold_start_drops_idle_and_domain_keeps_anomaly_and_morning(monkeypatch):
    _patch_collect_sources(
        monkeypatch,
        anom=[_cand("crisis", "anomaly:systolic_bp", domain="vitals", text="…")],
        morning=[_cand("praise", "morning")],
        motiv=[_cand("idle", "idle:sleep", domain="sleep")],
        domain=[_cand("domain", "domain:sleep", domain="sleep", llm="p")],
        has_data=False,
    )

    got = asyncio.run(pc.collect_candidates(1, db=object(), trigger="cron_morning"))

    assert {c.dedup_key for c in got} == {"anomaly:systolic_bp", "morning"}


# --------------------------------------------------------------------------- #
# deliver / ledger — sqlite
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def _sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, ChatMessage, ProactiveDelivery)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def test_deliver_writes_message_and_ledger_row():
    async def runner():
        async with _sqlite_session() as db:
            written = await pc.deliver_selected(
                1, db,
                [_cand("misses", "morning", domain="sleep", text="Доброе утро.")],
                trigger="login", today=date(2026, 8, 29),
            )
            assert len(written) == 1

            msg = (await db.execute(select(ChatMessage))).scalar_one()
            assert msg.is_read is False
            assert msg.request_type == "morning"

            led = (await db.execute(select(ProactiveDelivery))).scalar_one()
            assert (led.dedup_key, led.trigger, led.message_id) == ("morning", "login", msg.id)

            keys = await pc.sent_keys_today(db, 1, today=date(2026, 8, 29))
            assert keys == {"morning"}

    asyncio.run(runner())


def test_run_coordination_skips_key_already_in_ledger(monkeypatch):
    async def runner():
        async with _sqlite_session() as db:
            db.add(ProactiveDelivery(
                patient_id=1, context_date=date(2026, 8, 29), kind="misses",
                dedup_key="morning", domain=None, trigger="cron_morning",
            ))
            await db.commit()

            async def _collect(pid, db_, *, trigger):
                return [
                    _cand("misses", "morning", text="утро"),
                    _cand("idle", "idle:sleep", domain="sleep", text="сон"),
                ]

            monkeypatch.setattr(pc, "collect_candidates", _collect)

            written = await pc.run_proactive_coordination(
                1, db, trigger="login", today=date(2026, 8, 29)
            )

            assert [m.request_type for m in written] == ["motivator"]
            keys = await pc.sent_keys_today(db, 1, today=date(2026, 8, 29))
            assert keys == {"morning", "idle:sleep"}

    asyncio.run(runner())
