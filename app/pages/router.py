from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

# pages/router.py лежит в app/pages/
# parent.parent.parent -> корень проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

router = APIRouter(
    prefix="/p",
    tags=["pages"],
)


@router.get("/{patient_token}/home", include_in_schema=False)
async def serve_home_page(patient_token: str):
    """Главная страница пациента с карточками-сводками."""
    return FileResponse(FRONTEND_DIR / "patient" / "home.html")


@router.get("/{patient_token}/vitals", include_in_schema=False)
async def serve_vitals_page(patient_token: str):
    """
    Страница ввода показателей (АД, пульс, вес) для пациента.
    HTML сам достаёт patient_token из URL через JS.
    """
    return FileResponse(FRONTEND_DIR / "patient" / "vitals.html")


@router.get("/{patient_token}/education", include_in_schema=False)
async def serve_education_page(patient_token: str):
    """
    Старый экран обучения (education.html). Оставляем для совместимости.
    """
    return FileResponse(FRONTEND_DIR / "patient" / "education.html")


@router.get("/{patient_token}/education_overview", include_in_schema=False)
async def serve_education_overview_page(patient_token: str):
    """
    Новый навигатор обучения: список блоков и уроков.
    """
    return FileResponse(FRONTEND_DIR / "patient" / "education_overview.html")


@router.get("/{patient_token}/education_lesson", include_in_schema=False)
async def serve_education_lesson_page(patient_token: str):
    """
    Страница отдельного занятия (education_lesson.html).

    lesson_id берём из query-параметра (?lesson_id=...),
    patient_token — из URL (/p/{patient_token}/education_lesson).
    """
    return FileResponse(FRONTEND_DIR / "patient" / "education.html")


@router.get("/{patient_token}/education_test.html", include_in_schema=False)
async def serve_education_test_page(patient_token: str):
    """
    Страница прохождения теста по уроку.

    HTML один и тот же для всех пациентов, patient_token нужен только
    для привязки результатов к пациенту.
    """
    return FileResponse(FRONTEND_DIR / "patient" / "education_test.html")

@router.get("/{patient_token}/hads", include_in_schema=False)
async def serve_hads_page(patient_token: str):
    """
    Страница шкалы HADS.
    """
    return FileResponse(FRONTEND_DIR / "patient" / "hads.html")


@router.get("/{patient_token}/hads", include_in_schema=False)
async def serve_hads_page(patient_token: str):
    """
    Страница прохождения шкалы HADS.
    """
    return FileResponse(FRONTEND_DIR / "patient" / "hads.html")


@router.get("/{patient_token}/scales", include_in_schema=False)
async def serve_scales_overview_page(patient_token: str):
    """
    Страница обзора шкал (scales_overview).
    """
    return FileResponse(FRONTEND_DIR / "patient" / "scales_overview.html")

@router.get("/{patient_token}/kop25a", include_in_schema=False)
async def serve_kop25a_page(patient_token: str):
    """
    Страница анкеты КОП-25 А1 для пациента.

    HTML берёт patient_token из URL через JS.
    """
    return FileResponse(FRONTEND_DIR / "patient" / "kop25a.html")


@router.get("/{patient_token}/tobol", include_in_schema=False)
async def serve_tobol_page(patient_token: str):
    """Страница шкалы ТОБОЛ для пациента."""

    return FileResponse(FRONTEND_DIR / "patient" / "tobol.html")