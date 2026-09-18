"""Фаза 5 Track A — adherence по лекарствам и объединённая статистика практик.

Обе функции используют Postgres-специфичный SQL (LATERAL, generate_series) —
на sqlite не запускаются, поэтому единственный способ проверить логику — живая
БД (`hemo_db`, только тестовые пациенты).

NB: не переиспользуем `tests_py/conftest.py::async_session` — та фикстура
привязана к singleton-движку `core.db.engine.engine`, созданному один раз на
процесс. Второй/третий тест в этом файле получает от pytest-asyncio свой
event loop, а asyncpg-соединения из пула первого loop'а в нём не переиспользуются
(`InterfaceError: cannot perform operation: another operation is in progress`).
Поэтому здесь — свой движок на тест (тот же паттерн, что и в остальных файлах
tests_py, просто на Postgres вместо sqlite): создали, поработали, откатили
(commit нигде не вызываем — только flush), закрыли.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.education.models import Lesson, LessonTest, LessonTestResult, Practice as LessonPractice, PracticeLog
from app.medications.models import MedicationIntake, MedicationPrescription
from app.practices.models import PracticeCompletion, StandalonePractice
from app.researchers import service
from app.sleep_tracker.models import SleepRecord
from app.users.models import User
from app.vitals.models import BPMeasurement
from core.db.engine import DATABASE_URL


@asynccontextmanager
async def _pg_session_ctx():
    engine = create_async_engine(DATABASE_URL, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _make_patient(session, *, name: str) -> User:
    user = User(full_name=name)
    session.add(user)
    await session.flush()
    return user


def test_medication_adherence_counts_intakes_vs_frequency():
    async def runner():
        async with _pg_session_ctx() as session:
            patient = await _make_patient(session, name="Track A adherence patient")

            rx_day = date(2026, 6, 1)
            prescription = MedicationPrescription(
                patient_id=patient.id,
                medication_name="Track A Test Drug",
                dose=100,
                dose_unit="mg",
                frequency_times_per_day=2,
                intake_schedule=["morning", "evening"],
                route="oral",
                start_date=rx_day,
                end_date=rx_day,
                status="active",
            )
            session.add(prescription)
            await session.flush()

            session.add(
                MedicationIntake(
                    prescription_id=prescription.id,
                    patient_id=patient.id,
                    intake_datetime=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
                    actual_dose=100,
                    intake_slot="morning",
                )
            )
            await session.flush()

            rows = await service.get_medication_adherence(
                session, patient_id=patient.id, date_from=rx_day, date_to=rx_day
            )

            assert len(rows) == 1
            row = rows[0]
            assert row["patient_id"] == patient.id
            assert row["expected_total"] == 2
            assert row["actual_total"] == 1
            assert row["adherence_pct"] == 50.0

    asyncio.run(runner())


def test_medication_adherence_full_compliance_is_100_pct():
    async def runner():
        async with _pg_session_ctx() as session:
            patient = await _make_patient(session, name="Track A adherence full patient")

            rx_day = date(2026, 6, 2)
            prescription = MedicationPrescription(
                patient_id=patient.id,
                medication_name="Track A Test Drug 2",
                dose=50,
                dose_unit="mg",
                frequency_times_per_day=1,
                intake_schedule=["morning"],
                route="oral",
                start_date=rx_day,
                end_date=rx_day,
                status="active",
            )
            session.add(prescription)
            await session.flush()

            session.add(
                MedicationIntake(
                    prescription_id=prescription.id,
                    patient_id=patient.id,
                    intake_datetime=datetime(2026, 6, 2, 9, 0, tzinfo=timezone.utc),
                    actual_dose=50,
                    intake_slot="morning",
                )
            )
            await session.flush()

            rows = await service.get_medication_adherence(
                session, patient_id=patient.id, date_from=rx_day, date_to=rx_day
            )
            assert len(rows) == 1
            assert rows[0]["adherence_pct"] == 100.0

    asyncio.run(runner())


def test_practice_completions_union_tags_source():
    async def runner():
        async with _pg_session_ctx() as session:
            patient = await _make_patient(session, name="Track A practices patient")

            standalone = StandalonePractice(
                id="track_a_test_practice",
                module_id="101",
                type="breathing",
                title="Track A standalone practice",
                instruction=[],
                duration_seconds=60,
            )
            session.add(standalone)
            await session.flush()
            session.add(
                PracticeCompletion(patient_id=patient.id, practice_id=standalone.id, mood_after=3)
            )

            lesson = Lesson(code="track_a_test_lesson", topic="stress", title="Track A test lesson")
            session.add(lesson)
            await session.flush()
            lesson_practice = LessonPractice(
                lesson_id=lesson.id,
                title="Track A lesson practice",
                description_md="...",
            )
            session.add(lesson_practice)
            await session.flush()
            session.add(
                PracticeLog(
                    user_id=patient.id,
                    practice_id=lesson_practice.id,
                    success=True,
                    effect_rating=7,
                )
            )
            await session.flush()

            rows = await service.get_practice_completions(session, patient_id=patient.id)

            assert len(rows) == 2
            by_source = {r["source"]: r for r in rows}
            assert set(by_source) == {"standalone", "lesson"}
            assert by_source["standalone"]["mood_after"] == 3
            assert by_source["standalone"]["practice_id"] == "track_a_test_practice"
            assert by_source["lesson"]["success"] is True
            assert by_source["lesson"]["effect_rating"] == 7

    asyncio.run(runner())


def test_education_test_results_flatten_per_question():
    async def runner():
        async with _pg_session_ctx() as session:
            patient = await _make_patient(session, name="Track A education patient")

            lesson = Lesson(code="track_a_test_lesson_2", topic="stress", title="Track A test lesson 2")
            session.add(lesson)
            await session.flush()

            lesson_test = LessonTest(lesson_id=lesson.id, code="track_a_test_test", title="Track A test")
            session.add(lesson_test)
            await session.flush()

            session.add(
                LessonTestResult(
                    test_id=lesson_test.id,
                    user_id=patient.id,
                    score=1,
                    max_score=2,
                    passed=False,
                    answers_json=[
                        {"question_id": "q1", "chosen_option": 2, "is_correct": True},
                        {"question_id": "q2", "chosen_option": 1, "is_correct": False},
                    ],
                )
            )
            await session.flush()

            rows = await service.get_education_test_results(session, patient_id=patient.id)

            assert len(rows) == 2
            by_question = {r["question_id"]: r for r in rows}
            assert by_question["q1"]["is_correct"] is True
            assert by_question["q2"]["is_correct"] is False
            assert all(r["test_code"] == "track_a_test_test" for r in rows)
            assert all(r["score"] == 1.0 for r in rows)

    asyncio.run(runner())


def test_sleep_records_filters_by_date():
    async def runner():
        async with _pg_session_ctx() as session:
            patient = await _make_patient(session, name="Track A sleep patient")

            session.add(
                SleepRecord(
                    patient_id=patient.id,
                    sleep_date=date(2026, 6, 3),
                    sleep_onset="23:00",
                    wake_time="07:00",
                    tib_minutes=480,
                    tst_minutes=420,
                    sleep_efficiency_pct=87.5,
                    night_awakenings="1-2",
                    sleep_latency="fast",
                    morning_wellbeing="rested",
                )
            )
            await session.flush()

            rows = await service.get_sleep_records(
                session, patient_id=patient.id, date_from=date(2026, 6, 3), date_to=date(2026, 6, 3)
            )
            assert len(rows) == 1
            assert rows[0]["sleep_efficiency_pct"] == 87.5
            assert rows[0]["night_awakenings"] == "1-2"

            empty = await service.get_sleep_records(
                session, patient_id=patient.id, date_from=date(2026, 6, 4), date_to=date(2026, 6, 4)
            )
            assert empty == []

    asyncio.run(runner())


def test_vitals_records_bp_shapes_row():
    async def runner():
        async with _pg_session_ctx() as session:
            patient = await _make_patient(session, name="Track A vitals patient")

            session.add(BPMeasurement(user_id=patient.id, systolic=125, diastolic=82, pulse=70))
            await session.flush()

            rows = await service.get_vitals_records(session, vital_type="bp", patient_id=patient.id)
            assert len(rows) == 1
            assert rows[0]["systolic"] == 125
            assert rows[0]["diastolic"] == 82
            assert rows[0]["patient_id"] == patient.id

    asyncio.run(runner())


def test_vitals_records_rejects_unknown_type():
    async def runner():
        try:
            await service.get_vitals_records(None, vital_type="unknown")  # type: ignore[arg-type]
        except ValueError:
            return
        raise AssertionError("expected ValueError for unknown vital_type")

    asyncio.run(runner())
