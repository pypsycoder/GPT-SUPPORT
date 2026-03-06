# ============================================
# Researchers Schemas: Pydantic-схемы исследователя
# ============================================
# Схемы для создания пациентов, сброса PIN, ответы с данными.

"""Pydantic schemas for researcher module."""

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Optional
from uuid import UUID


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


class KdqolPointStatus(BaseModel):
    scale_code: str = "KDQOL_SF"  # KDQOL_SF | WCQ_LAZARUS | KOP_25A
    point_type: str               # T0 | T1 | T2
    is_completed: bool
    activated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class PatientListItem(BaseModel):
    id: int
    patient_number: Optional[int] = None
    full_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    is_locked: bool = False
    consent_personal_data: bool = False
    consent_bot_use: bool = False
    center_id: Optional[str] = None  # UUID as string for JSON
    center_name: Optional[str] = None
    center_city: Optional[str] = None
    kdqol_points: List[KdqolPointStatus] = []
    active_schedule_days: Optional[List[int]] = None   # ISO weekday numbers 1–7
    active_schedule_shift: Optional[str] = None        # morning|afternoon|evening

    model_config = ConfigDict(from_attributes=True)


class PatientDetail(PatientListItem):
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


class PatientCenterAssign(BaseModel):
    """Request body for assigning a dialysis center to a patient."""
    center_id: Optional[UUID] = None  # None = clear assignment


class BulkPatientActionRequest(BaseModel):
    """Request body for bulk delete or block actions on patients."""
    patient_ids: List[int]


# ---------------------------------------------------------------------------
# Chat log monitoring schemas
# ---------------------------------------------------------------------------

class ChatLogItem(BaseModel):
    """One row in the chat monitoring table — one LLM API call = one turn."""
    model_config = ConfigDict(protected_namespaces=())

    log_id: int
    patient_id: int
    created_at: datetime
    domain: Optional[str] = None
    request_type: Optional[str] = None
    model_tier: Optional[str] = None
    user_content: Optional[str] = None
    assistant_content: Optional[str] = None
    tokens_input: int = 0
    tokens_output: int = 0
    response_time_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None


class ChatLogsResponse(BaseModel):
    total: int
    safety_today: int
    avg_response_ms: float
    request_types_today: dict = {}
    items: List[ChatLogItem]


# ---------------------------------------------------------------------------
# Chat analytics schemas
# ---------------------------------------------------------------------------

class TokensByDate(BaseModel):
    date: str
    input: int
    output: int


class CohortItem(BaseModel):
    cohort_id: str
    center_id: str
    center_name: str
    shift: str
    weekdays: List[int]
    patient_count: int
    label: str


class ChatStatsResponse(BaseModel):
    tokens_by_date: List[TokensByDate]
    models_distribution: dict
    domains_distribution: dict
    activity_by_hour: dict = {}
    activity_by_weekday: dict = {}
    dialysis_vs_nondialysis: Optional[dict] = None
