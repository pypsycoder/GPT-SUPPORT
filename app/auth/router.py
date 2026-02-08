"""Authentication API endpoints for patients and researchers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Cookie, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

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
from app.auth.session_crud import create_session, delete_session
from app.auth.dependencies import (
    get_current_user,
    get_current_researcher,
)
from app.users.models import User
from app.researchers.models import Researcher

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie settings
_COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days


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
        status_code = 423 if "заблокирован" in error.lower() else 401
        return JSONResponse(
            status_code=status_code,
            content=AuthError(error=error).model_dump(),
        )

    # Create session in database
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    await create_session(
        session,
        token=token,
        user_id=user.id,
        expires_at=expires_at,
    )

    needs_consent = not user.consent_personal_data

    response.set_cookie(
        key="patient_session",
        value=token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )

    return PatientLoginResponse(needs_consent=needs_consent)


@router.post("/patient/logout")
async def patient_logout(
    response: Response,
    patient_session: Optional[str] = Cookie(None),
    db_session: AsyncSession = Depends(get_async_session),
):
    """Log out the current patient."""
    if patient_session:
        await delete_session(db_session, patient_session)
    response.delete_cookie("patient_session")
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
        "patient_token": user.patient_token,
        "consent_personal_data": user.consent_personal_data,
        "consent_bot_use": user.consent_bot_use,
    }


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
        return JSONResponse(
            status_code=401,
            content=AuthError(error=error).model_dump(),
        )

    # Create session in database
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    await create_session(
        session,
        token=token,
        researcher_id=researcher.id,
        expires_at=expires_at,
    )

    response.set_cookie(
        key="researcher_session",
        value=token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )

    return ResearcherLoginResponse()


@router.post("/researcher/logout")
async def researcher_logout(
    response: Response,
    researcher_session: Optional[str] = Cookie(None),
    db_session: AsyncSession = Depends(get_async_session),
):
    """Log out the current researcher."""
    if researcher_session:
        await delete_session(db_session, researcher_session)
    response.delete_cookie("researcher_session")
    return {"ok": True}


@router.get("/researcher/me")
async def researcher_me(researcher: Researcher = Depends(get_current_researcher)):
    """Return current researcher info."""
    return {
        "id": researcher.id,
        "username": researcher.username,
        "full_name": researcher.full_name,
    }
