# app/users/api.py
# HTTP-ручки для работы с пользователями.

from fastapi import APIRouter

router = APIRouter(
    prefix="/patients",
    tags=["patients"],
)
