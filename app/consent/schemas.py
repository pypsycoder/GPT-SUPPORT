"""Pydantic schemas for consent module."""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ConsentStatus(BaseModel):
    consent_personal_data: bool = False
    consent_bot_use: bool = False
    consent_given_at: Optional[datetime] = None
    needs_consent: bool = True


class ConsentAcceptRequest(BaseModel):
    consent_personal_data: bool = True
    consent_bot_use: bool = True


class ConsentRevokeRequest(BaseModel):
    """Какие согласия отозвать (хотя бы одно True)."""
    revoke_personal_data: bool = False
    revoke_bot_use: bool = False
