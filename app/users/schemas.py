# app/users/schemas.py
# Pydantic-схемы для работы с пользователями.

from pydantic import BaseModel, ConfigDict


# UserPublic
class UserPublic(BaseModel):
    """
    Публичное представление пациента для API.
    """
    id: int
    full_name: str | None = None
    age: int | None = None
    gender: str | None = None
    telegram_id: str
    consent_personal_data: bool = False
    consent_bot_use: bool = False

    model_config = ConfigDict(from_attributes=True)
