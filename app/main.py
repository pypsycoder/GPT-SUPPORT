from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import API_PREFIX, API_V1_PREFIX, api_path
from app.api_errors import register_api_exception_handlers
from app.core.config import load_environment


load_environment()

from app.auth.router import router as auth_router
from app.consent.router import router as consent_router
from app.dialysis.router import router as dialysis_router
from app.education.router import router as education_router
from app.medications.router import router as medications_router
from app.notifications.badges import router as badges_router
from app.pages.router import router as pages_router
from app.practices.router import router as practices_router
from app.profile.router import router as profile_router
from app.researchers.router import router as researcher_router
from app.routers.chat import router as chat_router
from app.routine.router import router as routine_router
from app.scales.routers import kdqol_patient_router, kdqol_researcher_router
from app.scales.routers import router as scales_router
from app.sleep_tracker.router import router as sleep_tracker_router
from app.users.api import router as users_api_router
from app.vitals.router import router as vitals_router


logger = logging.getLogger("gpt-support-api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("GPT Support API started.")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="GPT Support API", lifespan=lifespan)
    register_api_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost",
            "http://127.0.0.1",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount(
        "/frontend",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="frontend",
    )

    @app.get("/", include_in_schema=False)
    async def serve_root():
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/login")

    @app.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(vitals_router, prefix=API_V1_PREFIX)
    app.include_router(users_api_router, prefix=API_V1_PREFIX)
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    app.include_router(consent_router, prefix=API_V1_PREFIX)
    app.include_router(researcher_router, prefix=API_V1_PREFIX)
    app.include_router(dialysis_router, prefix=API_V1_PREFIX)
    app.include_router(sleep_tracker_router, prefix=API_V1_PREFIX)
    app.include_router(routine_router, prefix=API_V1_PREFIX)
    app.include_router(medications_router, prefix=API_V1_PREFIX)
    app.include_router(badges_router, prefix=API_V1_PREFIX)
    app.include_router(practices_router, prefix=API_V1_PREFIX)
    app.include_router(chat_router, prefix=api_path("/chat"), tags=["chat"])
    app.include_router(pages_router)
    app.include_router(education_router, prefix=api_path("/education"))
    app.include_router(scales_router, prefix=api_path("/scales"), tags=["scales"])
    app.include_router(profile_router, prefix=api_path("/profile"), tags=["profile"])
    app.include_router(kdqol_patient_router, prefix=API_V1_PREFIX)
    app.include_router(kdqol_researcher_router, prefix=API_V1_PREFIX)

    # Legacy compatibility during API prefix migration.
    app.include_router(medications_router, prefix=API_PREFIX)
    app.include_router(badges_router, prefix=API_PREFIX)
    app.include_router(practices_router, prefix=API_PREFIX)
    app.include_router(chat_router, prefix=api_path("/chat", legacy=True), tags=["chat-legacy"])

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    run()
