# ============================================
# Pages Router: Маршруты статических HTML-страниц
# ============================================
# Раздача HTML-страниц пациента и исследователя через FastAPI.
# Включает session-based маршруты (/patient/...) 

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

# pages/router.py лежит в app/pages/
# parent.parent.parent -> корень проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

router = APIRouter(tags=["pages"])


# ============================================
#   Авторизация и согласия — публичные страницы
# ============================================

@router.get("/login", include_in_schema=False)
async def serve_login_page():
    """Страница входа пациента (PIN + ID)."""
    return FileResponse(FRONTEND_DIR / "patient" / "login.html")


@router.get("/consent", include_in_schema=False)
async def serve_consent_page():
    """Страница согласий пациента."""
    return FileResponse(FRONTEND_DIR / "patient" / "consent.html")


# ============================================
#   Исследователь — страницы
# ============================================

@router.get("/researcher/login", include_in_schema=False)
async def serve_researcher_login():
    """Страница входа исследователя."""
    return FileResponse(FRONTEND_DIR / "researcher" / "login.html")


@router.get("/researcher/dashboard", include_in_schema=False)
async def serve_researcher_dashboard():
    """Панель исследователя."""
    return FileResponse(FRONTEND_DIR / "researcher" / "dashboard.html")


@router.get("/researcher/centers", include_in_schema=False)
async def serve_researcher_centers():
    """Центры диализа."""
    return FileResponse(FRONTEND_DIR / "researcher" / "centers.html")


@router.get("/researcher/import/schedules", include_in_schema=False)
async def serve_researcher_import_schedules():
    """Импорт расписаний диализа."""
    return FileResponse(FRONTEND_DIR / "researcher" / "import_schedules.html")


# ============================================
#   Пациент — session-based страницы (/patient/...)
# ============================================

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


@router.get("/patient/sleep_tracker", include_in_schema=False)
async def serve_patient_sleep_tracker():
    """Рутинная оценка сна (Sleep Tracker)."""
    return FileResponse(FRONTEND_DIR / "patient" / "sleep_tracker.html")
