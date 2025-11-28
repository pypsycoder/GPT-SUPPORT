## Pydantic-схемы для работы с обучающими материалами (education).

# app/education/schemas.py

from pydantic import BaseModel
from typing import Optional


# EducationItem – минимальная схема обучающего материала
class EducationItem(BaseModel):
    """
    Обучающий материал для пациента.

    Минимальный набор полей для MVP:
    - id: внутренний идентификатор карточки
    - topic: тема/блок (например, "stress", "sleep")
    - content: содержимое (Markdown/текст)
    """
    id: int
    topic: str
    content: str

    # При желании потом добавим:
    # title: Optional[str]
    # short: Optional[str]
    # order: Optional[int]
