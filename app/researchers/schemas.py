"""Pydantic schemas for researcher module."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Patient management schemas
# ---------------------------------------------------------------------------

class PatientCreateRequest(BaseModel):
    full_name: str
    age: Optional[int] = None
    gender: Optional[str] = None


class PatientCreateResponse(BaseModel):
    """Response after creating a patient — includes plaintext PIN (shown once)."""
    id: int
    patient_number: int
    pin: str  # plaintext, shown only at creation time
    full_name: Optional[str] = None


class PatientListItem(BaseModel):
    id: int
    patient_number: Optional[int] = None
    full_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    is_locked: bool = False
    consent_personal_data: bool = False
    consent_bot_use: bool = False

    model_config = ConfigDict(from_attributes=True)


class PatientDetail(PatientListItem):
    patient_token: Optional[str] = None
    telegram_id: Optional[str] = None
    consent_given_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PatientCardData(BaseModel):
    """Data needed to print a patient card."""
    patient_number: int
    pin: str  # plaintext — only available at creation or reset


class PinResetResponse(BaseModel):
    patient_number: int
    new_pin: str
