# app/pages/router.py

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

# Базовый путь к фронтенду:
# pages/router.py лежит в app/pages/
# parent.parent -> app/
# parent.parent.parent -> корень проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

router = APIRouter(
    prefix="/p",
    tags=["pages"],  # так они появятся в отдельном разделе /docs
)


@router.get("/{patient_token}/vitals")
async def serve_vitals_page(patient_token: str):
    """
    Страница ввода показателей (АД, пульс, вес) для пациента.
    HTML сам достаёт patient_token из URL через JS.
    """
    return FileResponse(FRONTEND_DIR / "patient" / "vitals.html")


@router.get("/{patient_token}/education")
async def serve_education_page(patient_token: str):
    """
    Страница обучающих материалов для пациента.
    Пока токен используется только в URL для единообразия.
    """
    return FileResponse(FRONTEND_DIR / "patient" / "education.html")
