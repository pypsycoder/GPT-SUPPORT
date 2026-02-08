"""Pydantic schemas for authentication requests/responses."""

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Patient auth
# ---------------------------------------------------------------------------

class PatientLoginRequest(BaseModel):
    patient_number: int
    pin: str


class PatientLoginResponse(BaseModel):
    ok: bool = True
    needs_consent: bool = False
    message: str = "Вход выполнен"


# ---------------------------------------------------------------------------
# Researcher auth
# ---------------------------------------------------------------------------

class ResearcherLoginRequest(BaseModel):
    username: str
    password: str


class ResearcherLoginResponse(BaseModel):
    ok: bool = True
    message: str = "Вход выполнен"


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------

class AuthError(BaseModel):
    ok: bool = False
    error: str
