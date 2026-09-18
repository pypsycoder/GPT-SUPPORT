"""Фаза 5 Track A — роутер-уровень: /researcher/scales/items(+/export).

sqlite in-memory (ScaleItemResponse — чистый ORM select, без Postgres-специфики),
по образцу tests_py/researchers/test_llm_provider.py. Эндпоинты
medications/adherence и practices/completions используют Postgres-специфичный
SQL (LATERAL, generate_series) — их бизнес-логика проверена отдельно, на
реальной БД, в test_track_a_trackers.py.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api_errors import register_api_exception_handlers
from app.auth.dependencies import get_current_researcher
from app.researchers.models import Researcher
from app.researchers.router import router as researcher_router
from app.researchers import service
from app.scales.models import ScaleItemResponse
from core.db.session import get_async_session
from tests_py.sqlite_schema import create_tables


@asynccontextmanager
async def _session_ctx():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"scales": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, ScaleItemResponse)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _client(session, researcher):
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    app = FastAPI()
    register_api_exception_handlers(app)
    app.include_router(researcher_router, prefix="/api/v1")

    async def _sess():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_async_session] = _sess
    app.dependency_overrides[get_current_researcher] = lambda: researcher
    return TestClient(app)


def _seed_item(session, **overrides):
    from uuid import uuid4

    defaults = dict(
        id=uuid4(),
        user_id=1,
        result_id=uuid4(),
        scale_code="HADS",
        scale_version="1.0",
        question_id="q1",
        answer_value="2",
        measured_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    session.add(ScaleItemResponse(**defaults))


def test_list_scale_items_filters_by_patient_and_scale(monkeypatch):
    async def runner():
        async with _session_ctx() as seed:
            _seed_item(seed, user_id=1, scale_code="HADS", question_id="q1", answer_value="2")
            _seed_item(seed, user_id=1, scale_code="PSS10", question_id="q1", answer_value="1")
            _seed_item(seed, user_id=2, scale_code="HADS", question_id="q1", answer_value="3")
            await seed.commit()

            researcher = Researcher(id=1, username="r", password_hash="x")
            client = _client(seed, researcher)

            resp = client.get("/api/v1/researcher/scales/items", params={"patient_id": 1, "scale_code": "HADS"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert len(body) == 1
            assert body[0]["patient_id"] == 1
            assert body[0]["scale_code"] == "HADS"
            assert body[0]["answer_value"] == "2"

    asyncio.run(runner())


def test_export_scale_items_csv_and_json(monkeypatch):
    async def runner():
        async with _session_ctx() as seed:
            _seed_item(seed, user_id=5, scale_code="WCQ_LAZARUS", question_id="q1", answer_value="a")
            await seed.commit()

            researcher = Researcher(id=1, username="r", password_hash="x")
            client = _client(seed, researcher)

            csv_resp = client.get(
                "/api/v1/researcher/scales/items/export", params={"patient_id": 5, "format": "csv"}
            )
            assert csv_resp.status_code == 200
            rows = list(csv.reader(io.StringIO(csv_resp.text)))
            assert rows[0] == [
                "patient_id", "scale_code", "scale_version", "question_id", "answer_value", "measured_at",
            ]
            assert rows[1][0] == "5"
            assert rows[1][3] == "q1"

            json_resp = client.get(
                "/api/v1/researcher/scales/items/export", params={"patient_id": 5, "format": "json"}
            )
            assert json_resp.status_code == 200
            data = json.loads(json_resp.text)
            assert len(data) == 1
            assert data[0]["answer_value"] == "a"

    asyncio.run(runner())


# ---------------------------------------------------------------------------
# build_export_response — форматирование, без БД
# ---------------------------------------------------------------------------

def test_build_export_response_csv_streams_header_and_rows():
    rows = [
        {"a": 1, "b": "x", "c": None},
        {"a": 2, "b": "y", "c": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    ]
    resp = service.build_export_response(rows, ["a", "b", "c"], format="csv", filename_prefix="unit")
    assert resp.media_type.startswith("text/csv")

    async def collect():
        return [chunk async for chunk in resp.body_iterator]

    chunks = asyncio.run(collect())
    text_out = "".join(chunks)
    parsed = list(csv.reader(io.StringIO(text_out)))
    assert parsed[0] == ["a", "b", "c"]
    assert parsed[1] == ["1", "x", ""]
    assert parsed[2] == ["2", "y", "2026-01-01T00:00:00+00:00"]


def test_build_export_response_json_serializes_rows():
    rows = [{"a": 1, "b": datetime(2026, 1, 1, tzinfo=timezone.utc)}]
    resp = service.build_export_response(rows, ["a", "b"], format="json", filename_prefix="unit")
    assert resp.media_type == "application/json"

    async def collect():
        return [chunk async for chunk in resp.body_iterator]

    chunks = asyncio.run(collect())
    data = json.loads("".join(chunks))
    assert data == [{"a": 1, "b": "2026-01-01T00:00:00+00:00"}]
