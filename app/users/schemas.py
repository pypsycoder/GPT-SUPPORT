# app/users/schemas.py
# Pydantic-схемы для работы с пользователями.

from pydantic import BaseModel


# UserPublic
class UserPublic(BaseModel):
    """
    Публичное представление пациента для API.

    Используется, когда фронтенду нужно знать:
    - id пользователя,
    - ФИО (если есть),
    - telegram_id,
    - patient_token (для дальнейших ссылок).
    """
    id: int
    full_name: str | None = None
    telegram_id: str
    patient_token: str

    class Config:
        from_attributes = True  # pydantic v2: подтягивать данные из ORM-модели
