# ============================================
# Auth Router: Эндпоинты авторизации
# ============================================
# Login/logout для пациентов (PIN) и исследователей (пароль).

"""Authentication API endpoints for patients and researchers."""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api_errors import api_error_response
from app.auth.csrf import CSRF_COOKIE_NAME, generate_csrf_token, require_csrf
from core.db.session import get_async_session
from app.auth.schemas import (
    PatientLoginRequest,
    PatientLoginResponse,
    ResearcherLoginRequest,
    ResearcherLoginResponse,
    AuthError,
)
from app.auth.service import authenticate_patient, authenticate_researcher
from app.auth.security import generate_session_token
from app.auth.session_crud import (
    cleanup_sessions,
    create_session,
    revoke_researcher_sessions,
    revoke_session,
    revoke_user_sessions,
)
from app.auth.dependencies import (
    get_current_user,
    get_current_researcher,
)
from app.auth.session_policy import (
    COOKIE_HTTP_ONLY,
    COOKIE_PATH,
    COOKIE_SAMESITE,
    SESSION_TTL,
    session_cookie_secure,
)
from app.users.models import User
from app.researchers.models import Researcher

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_MAX_AGE = int(SESSION_TTL.total_seconds())


def _client_ip(request: Request) -> Optional[str]:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client is None:
        return None
    return request.client.host


def _set_session_cookie(response: Response, *, key: str, value: str) -> None:
    response.set_cookie(
        key=key,
        value=value,
        max_age=_COOKIE_MAX_AGE,
        httponly=COOKIE_HTTP_ONLY,
        secure=session_cookie_secure(),
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )


def _set_csrf_cookie(response: Response, *, value: str) -> None:
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=value,
        max_age=_COOKIE_MAX_AGE,
        httponly=False,
        secure=session_cookie_secure(),
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )


def _clear_session_cookie(response: Response, *, key: str) -> None:
    response.delete_cookie(
        key,
        path=COOKIE_PATH,
        secure=session_cookie_secure(),
        httponly=COOKIE_HTTP_ONLY,
        samesite=COOKIE_SAMESITE,
    )


def _clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path=COOKIE_PATH,
        secure=session_cookie_secure(),
        httponly=False,
        samesite=COOKIE_SAMESITE,
    )


# ---------------------------------------------------------------------------
# Patient endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/patient/login",
    response_model=PatientLoginResponse,
    responses={401: {"model": AuthError}, 423: {"model": AuthError}},
)
async def patient_login(
    body: PatientLoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
):
    """Authenticate a patient by patient_number + PIN."""
    user, error = await authenticate_patient(
        session,
        patient_number=body.patient_number,
        pin=body.pin,
    )

    if user is None:
        status_code = 423 if "??????" in error.lower() else 401
        return api_error_response(
            status_code=status_code,
            code="account_locked" if status_code == 423 else "invalid_credentials",
            message=error,
        )

    # Create session in database
    token = generate_session_token()
    csrf_token = generate_csrf_token()
    expires_at = datetime.now(timezone.utc) + SESSION_TTL
    await cleanup_sessions(session)
    await revoke_user_sessions(session, user.id, reason="rotated_on_login")
    await create_session(
        session,
        token=token,
        user_id=user.id,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )

    needs_consent = not user.consent_personal_data
    needs_onboarding = not user.is_onboarded

    _set_session_cookie(response, key="patient_session", value=token)
    _set_csrf_cookie(response, value=csrf_token)

    return PatientLoginResponse(needs_consent=needs_consent, needs_onboarding=needs_onboarding)


@router.post("/patient/logout")
async def patient_logout(
    response: Response,
    _csrf: None = Depends(require_csrf),
    patient_session: Optional[str] = Cookie(None),
    db_session: AsyncSession = Depends(get_async_session),
):
    """Log out the current patient."""
    if patient_session:
        await revoke_session(db_session, patient_session, reason="patient_logout")
    await cleanup_sessions(db_session)
    _clear_session_cookie(response, key="patient_session")
    _clear_csrf_cookie(response)
    return {"ok": True}


@router.get("/patient/me")
async def patient_me(user: User = Depends(get_current_user)):
    """Return current patient info."""
    return {
        "id": user.id,
        "full_name": user.full_name,
        "age": user.age,
        "gender": user.gender,
        "patient_number": user.patient_number,
        "consent_personal_data": user.consent_personal_data,
        "consent_bot_use": user.consent_bot_use,
        "is_onboarded": user.is_onboarded,
    }


@router.post("/patient/onboarding/complete")
async def patient_onboarding_complete(
    _csrf: None = Depends(require_csrf),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Mark onboarding as completed for the current patient."""
    user.is_onboarded = True
    await session.flush()
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Researcher endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/researcher/login",
    response_model=ResearcherLoginResponse,
    responses={401: {"model": AuthError}},
)
async def researcher_login(
    body: ResearcherLoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
):
    """Authenticate a researcher by username + password."""
    researcher, error = await authenticate_researcher(
        session,
        username=body.username,
        password=body.password,
    )

    if researcher is None:
        return api_error_response(
            status_code=401,
            code="invalid_credentials",
            message=error,
        )

    # Create session in database
    token = generate_session_token()
    csrf_token = generate_csrf_token()
    expires_at = datetime.now(timezone.utc) + SESSION_TTL
    await cleanup_sessions(session)
    await revoke_researcher_sessions(session, researcher.id, reason="rotated_on_login")
    await create_session(
        session,
        token=token,
        researcher_id=researcher.id,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )

    _set_session_cookie(response, key="researcher_session", value=token)
    _set_csrf_cookie(response, value=csrf_token)

    return ResearcherLoginResponse()


@router.post("/researcher/logout")
async def researcher_logout(
    response: Response,
    _csrf: None = Depends(require_csrf),
    researcher_session: Optional[str] = Cookie(None),
    db_session: AsyncSession = Depends(get_async_session),
):
    """Log out the current researcher."""
    if researcher_session:
        await revoke_session(db_session, researcher_session, reason="researcher_logout")
    await cleanup_sessions(db_session)
    _clear_session_cookie(response, key="researcher_session")
    _clear_csrf_cookie(response)
    return {"ok": True}


@router.get("/researcher/me")
async def researcher_me(researcher: Researcher = Depends(get_current_researcher)):
    """Return current researcher info."""
    return {
        "id": researcher.id,
        "username": researcher.username,
        "full_name": researcher.full_name,
    }
