from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import API_PREFIX, API_V1_PREFIX
from app.api_errors import register_api_exception_handlers
from app.auth.dependencies import get_current_researcher, get_current_user
from app.auth.models import Session
from app.auth.router import router as auth_router
from app.auth.security import hash_password, hash_pin
from app.consent.router import router as consent_router
from app.main import create_app
from app.profile.router import router as profile_router
from app.researchers.models import Researcher
from app.users.models import User
from core.db.session import get_async_session


@asynccontextmanager
async def auth_session_ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(Researcher.__table__.create)
        await conn.run_sync(Session.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def build_test_app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = FastAPI()
    register_api_exception_handlers(app)
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    app.include_router(consent_router, prefix=API_V1_PREFIX)
    app.include_router(profile_router, prefix=f"{API_V1_PREFIX}/profile")

    @app.get("/api/v1/probe/patient")
    async def probe_patient(_user: User = Depends(get_current_user)) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/probe/researcher")
    async def probe_researcher(
        _researcher: Researcher = Depends(get_current_researcher),
    ) -> dict[str, bool]:
        return {"ok": True}

    async def override_session() -> AsyncSession:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_session
    return app


async def seed_auth_data(session: AsyncSession) -> tuple[User, Researcher]:
    user = User(
        telegram_id="patient-1",
        full_name="Patient One",
        consent_personal_data=True,
        consent_bot_use=True,
        patient_number=1001,
        pin_hash=hash_pin("1234"),
        is_onboarded=True,
    )
    researcher = Researcher(
        username="researcher",
        password_hash=hash_password("secret"),
        full_name="Researcher One",
        is_active=True,
    )
    session.add(user)
    session.add(researcher)
    await session.commit()
    await session.refresh(user)
    await session.refresh(researcher)
    return user, researcher


def test_login_rotation_revokes_previous_patient_session():
    async def runner():
        async with auth_session_ctx() as seed_session:
            user, _ = await seed_auth_data(seed_session)
            session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = build_test_app(session_factory)

            async with session_factory() as db:
                db.add(
                    Session(
                        token="old-token-hash",
                        user_id=user.id,
                        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                        last_seen_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()

            client = TestClient(app)
            resp = client.post(
                "/api/v1/auth/patient/login",
                json={"patient_number": 1001, "pin": "1234"},
                headers={"user-agent": "pytest"},
            )

            assert resp.status_code == 200
            assert "patient_session" in resp.cookies
            assert "csrf_token" in resp.cookies

            async with session_factory() as db:
                rows = (
                    await db.execute(
                        select(Session).where(Session.user_id == user.id).order_by(Session.created_at)
                    )
                ).scalars().all()
                assert len(rows) == 2
                revoked_rows = [row for row in rows if row.revoked_at is not None]
                active_rows = [row for row in rows if row.revoked_at is None]
                assert len(revoked_rows) == 1
                assert revoked_rows[0].revoked_reason == "rotated_on_login"
                assert len(active_rows) == 1
                assert active_rows[0].user_agent == "pytest"

    asyncio.run(runner())


def test_sensitive_endpoints_require_csrf_when_enabled():
    async def runner():
        previous = os.environ.get("CSRF_ENABLED")
        os.environ["CSRF_ENABLED"] = "true"
        try:
            async with auth_session_ctx() as seed_session:
                await seed_auth_data(seed_session)
                session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
                app = build_test_app(session_factory)
                client = TestClient(app)

                login = client.post(
                    "/api/v1/auth/patient/login",
                    json={"patient_number": 1001, "pin": "1234"},
                )
                assert login.status_code == 200
                csrf_token = login.cookies.get("csrf_token")
                assert csrf_token

                forbidden = client.patch(
                    "/api/v1/profile/update",
                    json={"full_name": "Blocked"},
                )
                assert forbidden.status_code == 403
                assert forbidden.json()["error_code"] == "forbidden"

                allowed = client.patch(
                    "/api/v1/profile/update",
                    json={"full_name": "Allowed"},
                    headers={"X-CSRF-Token": csrf_token},
                )
                assert allowed.status_code == 200
                assert allowed.json()["full_name"] == "Allowed"
        finally:
            if previous is None:
                os.environ.pop("CSRF_ENABLED", None)
            else:
                os.environ["CSRF_ENABLED"] = previous

    asyncio.run(runner())


def test_role_boundaries_reject_cross_role_cookies():
    async def runner():
        async with auth_session_ctx() as seed_session:
            await seed_auth_data(seed_session)
            session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = build_test_app(session_factory)
            client = TestClient(app)

            patient_login = client.post(
                "/api/v1/auth/patient/login",
                json={"patient_number": 1001, "pin": "1234"},
            )
            assert patient_login.status_code == 200

            resp = client.get("/api/v1/probe/researcher")
            assert resp.status_code == 401

            client.cookies.clear()
            researcher_login = client.post(
                "/api/v1/auth/researcher/login",
                json={"username": "researcher", "password": "secret"},
            )
            assert researcher_login.status_code == 200

            resp = client.get("/api/v1/probe/patient")
            assert resp.status_code == 401

    asyncio.run(runner())


def test_consent_revoke_requires_authenticated_patient_and_uses_error_envelope():
    async def runner():
        async with auth_session_ctx() as seed_session:
            await seed_auth_data(seed_session)
            session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = build_test_app(session_factory)
            client = TestClient(app)

            unauthorized = client.post(
                "/api/v1/consent/revoke",
                json={"revoke_personal_data": True},
            )
            assert unauthorized.status_code == 401
            unauthorized_payload = unauthorized.json()
            assert unauthorized_payload["ok"] is False
            assert unauthorized_payload["error_code"] == "unauthorized"
            assert isinstance(unauthorized_payload["detail"], str)

            client.post(
                "/api/v1/auth/patient/login",
                json={"patient_number": 1001, "pin": "1234"},
            )
            invalid = client.post(
                "/api/v1/consent/revoke",
                json={},
            )
            assert invalid.status_code == 400
            invalid_payload = invalid.json()
            assert invalid_payload["ok"] is False
            assert invalid_payload["error_code"] == "bad_request"
            assert isinstance(invalid_payload["error"], str)

    asyncio.run(runner())


def test_profile_update_requires_patient_auth_and_updates_profile():
    async def runner():
        async with auth_session_ctx() as seed_session:
            await seed_auth_data(seed_session)
            session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = build_test_app(session_factory)
            client = TestClient(app)

            unauthorized = client.patch(
                "/api/v1/profile/update",
                json={"full_name": "Updated Name"},
            )
            assert unauthorized.status_code == 401
            unauthorized_payload = unauthorized.json()
            assert unauthorized_payload["error_code"] == "unauthorized"

            client.post(
                "/api/v1/auth/patient/login",
                json={"patient_number": 1001, "pin": "1234"},
            )
            resp = client.patch(
                "/api/v1/profile/update",
                json={"full_name": "Updated Name", "age": 41, "gender": "male"},
            )
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["full_name"] == "Updated Name"
            assert payload["age"] == 41
            assert payload["gender"] == "male"

    asyncio.run(runner())


def test_profile_update_allows_nullable_telegram_id_in_response():
    async def runner():
        async with auth_session_ctx() as seed_session:
            user, _ = await seed_auth_data(seed_session)
            user.telegram_id = None
            await seed_session.commit()

            session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = build_test_app(session_factory)
            client = TestClient(app)

            client.post(
                "/api/v1/auth/patient/login",
                json={"patient_number": 1001, "pin": "1234"},
            )
            resp = client.patch(
                "/api/v1/profile/update",
                json={"full_name": "No Telegram"},
            )
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["full_name"] == "No Telegram"
            assert payload["telegram_id"] is None

    asyncio.run(runner())


def test_profile_update_validation_errors_use_common_api_shape():
    async def runner():
        async with auth_session_ctx() as seed_session:
            await seed_auth_data(seed_session)
            session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = build_test_app(session_factory)
            client = TestClient(app)

            client.post(
                "/api/v1/auth/patient/login",
                json={"patient_number": 1001, "pin": "1234"},
            )
            resp = client.patch(
                "/api/v1/profile/update",
                json={"age": 999, "gender": "other"},
            )
            assert resp.status_code == 422
            payload = resp.json()
            assert payload["ok"] is False
            assert payload["error_code"] == "validation_error"
            assert payload["detail"] == "Validation failed"
            assert payload["error_meta"]["details"]

    asyncio.run(runner())


def test_main_registers_v1_and_legacy_routes_for_migration():
    app = create_app()
    paths = {route.path for route in app.routes}

    assert f"{API_V1_PREFIX}/patient/medications/prescriptions" in paths
    assert f"{API_PREFIX}/patient/medications/prescriptions" in paths
    assert f"{API_V1_PREFIX}/chat/message" in paths
    assert f"{API_PREFIX}/chat/message" in paths
