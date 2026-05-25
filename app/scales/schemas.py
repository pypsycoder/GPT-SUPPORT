from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ScaleAnswerIn(BaseModel):
    question_id: str
    option_id: str


class PsqiAnswerIn(BaseModel):
    question_id: str
    value: Any
