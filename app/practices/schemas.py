from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PracticeOut(BaseModel):
    id: str
    module_id: str
    type: str
    icf_domain: Optional[str] = None
    context: Optional[str] = None
    title: str
    tagline: Optional[str] = None
    instruction: List[str]
    duration_seconds: int
    completion_prompt: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


class CompleteIn(BaseModel):
    mood_after: Optional[int] = None  # 1=😔 2=😐 3=😊


class CompleteOut(BaseModel):
    success: bool
    practice_id: str
    completed_at: datetime
