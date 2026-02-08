from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

# pages/router.py лежит в app/pages/
# parent.parent.parent -> корень проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

router = APIRouter(tags=["pages"])


# =====================================================================
# Авторизация и согласия — публичные страницы
# =====================================================================

@router.get("/login", include_in_schema=False)
async def serve_login_page():
    """Страница входа пациента (PIN + ID)."""
    return FileResponse(FRONTEND_DIR / "patient" / "login.html")


@router.get("/consent", include_in_schema=False)
async def serve_consent_page():
    """Страница согласий пациента."""
    return FileResponse(FRONTEND_DIR / "patient" / "consent.html")


# =====================================================================
# Исследователь — страницы
# =====================================================================

@router.get("/researcher/login", include_in_schema=False)
async def serve_researcher_login():
    """Страница входа исследователя."""
    return FileResponse(FRONTEND_DIR / "researcher" / "login.html")


@router.get("/researcher/dashboard", include_in_schema=False)
async def serve_researcher_dashboard():
    """Панель исследователя."""
    return FileResponse(FRONTEND_DIR / "researcher" / "dashboard.html")


# =====================================================================
# Пациент — session-based страницы (/patient/...)
# =====================================================================

@router.get("/patient/home", include_in_schema=False)
async def serve_patient_home():
    """Главная страница пациента (session-based)."""
    return FileResponse(FRONTEND_DIR / "patient" / "home.html")


@router.get("/patient/vitals", include_in_schema=False)
async def serve_patient_vitals():
    """Страница витальных показателей."""
    return FileResponse(FRONTEND_DIR / "patient" / "vitals.html")


@router.get("/patient/education", include_in_schema=False)
async def serve_patient_education():
    """Страница обучения."""
    return FileResponse(FRONTEND_DIR / "patient" / "education.html")


@router.get("/patient/education_overview", include_in_schema=False)
async def serve_patient_education_overview():
    """Навигатор обучения."""
    return FileResponse(FRONTEND_DIR / "patient" / "education_overview.html")


@router.get("/patient/education_lesson", include_in_schema=False)
async def serve_patient_education_lesson():
    """Страница урока."""
    return FileResponse(FRONTEND_DIR / "patient" / "education.html")


@router.get("/patient/education_test", include_in_schema=False)
async def serve_patient_education_test():
    """Страница теста."""
    return FileResponse(FRONTEND_DIR / "patient" / "education_test.html")


@router.get("/patient/hads", include_in_schema=False)
async def serve_patient_hads():
    """Шкала HADS."""
    return FileResponse(FRONTEND_DIR / "patient" / "hads.html")


@router.get("/patient/scales", include_in_schema=False)
async def serve_patient_scales():
    """Обзор шкал."""
    return FileResponse(FRONTEND_DIR / "patient" / "scales_overview.html")


@router.get("/patient/kop25a", include_in_schema=False)
async def serve_patient_kop25a():
    """Анкета КОП-25 А1."""
    return FileResponse(FRONTEND_DIR / "patient" / "kop25a.html")


@router.get("/patient/tobol", include_in_schema=False)
async def serve_patient_tobol():
    """Шкала ТОБОЛ."""
    return FileResponse(FRONTEND_DIR / "patient" / "tobol.html")


@router.get("/patient/psqi", include_in_schema=False)
async def serve_patient_psqi():
    """Опросник PSQI."""
    return FileResponse(FRONTEND_DIR / "patient" / "psqi.html")


@router.get("/patient/profile", include_in_schema=False)
async def serve_patient_profile():
    """Профиль пациента."""
    return FileResponse(FRONTEND_DIR / "patient" / "profile.html")


# =====================================================================
# Legacy — старые маршруты /p/{token}/... (обратная совместимость)
# =====================================================================

_LEGACY_PREFIX = "/p"
_legacy = APIRouter(prefix=_LEGACY_PREFIX, tags=["pages-legacy"])


@_legacy.get("/{patient_token}/home", include_in_schema=False)
async def legacy_home_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "home.html")


@_legacy.get("/{patient_token}/vitals", include_in_schema=False)
async def legacy_vitals_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "vitals.html")


@_legacy.get("/{patient_token}/education", include_in_schema=False)
async def legacy_education_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "education.html")


@_legacy.get("/{patient_token}/education_overview", include_in_schema=False)
async def legacy_education_overview_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "education_overview.html")


@_legacy.get("/{patient_token}/education_lesson", include_in_schema=False)
async def legacy_education_lesson_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "education.html")


@_legacy.get("/{patient_token}/education_test.html", include_in_schema=False)
async def legacy_education_test_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "education_test.html")


@_legacy.get("/{patient_token}/hads", include_in_schema=False)
async def legacy_hads_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "hads.html")


@_legacy.get("/{patient_token}/scales", include_in_schema=False)
async def legacy_scales_overview_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "scales_overview.html")


@_legacy.get("/{patient_token}/kop25a", include_in_schema=False)
async def legacy_kop25a_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "kop25a.html")


@_legacy.get("/{patient_token}/tobol", include_in_schema=False)
async def legacy_tobol_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "tobol.html")


@_legacy.get("/{patient_token}/psqi", include_in_schema=False)
async def legacy_psqi_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "psqi.html")


@_legacy.get("/{patient_token}/profile", include_in_schema=False)
async def legacy_profile_page(patient_token: str):
    return FileResponse(FRONTEND_DIR / "patient" / "profile.html")


# Include legacy router
router.include_router(_legacy)
