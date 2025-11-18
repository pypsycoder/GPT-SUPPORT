from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text

from app.models import Base
from app.vitals.router import router as vitals_router
from core.db.engine import engine

app = FastAPI(title="GPT Support API")
app.include_router(vitals_router)


@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS vitals"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS users"))
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run()
