import asyncio
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

os.environ.setdefault("APP_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.models import Base  # noqa: E402
from app.scales.models import ScaleResult  # noqa: E402
from app.scales.routers import router as scales_router  # noqa: E402
from app.scales.services import calculate_tobol_result  # noqa: E402
from app.scales.config.tobol import TOBOL_CONFIG  # noqa: E402
from app.users.models import User  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from core.db.session import get_async_session  # noqa: E402


def test_calculate_tobol_result_anxious_type():
    answers = [
        {"question_id": "I_7", "value": 1},
        {"question_id": "III_10", "value": 1},
        {"question_id": "V_1", "value": 1},
    ]

    result, _ = calculate_tobol_result(TOBOL_CONFIG, answers)

    assert result["total_score"] == 12
    assert result["subscales"]["T"]["score"] == 12
    assert "Тревожный" in result["summary"]


def test_submit_tobol_creates_result():
    async def runner():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            future=True,
            execution_options={
                "schema_translate_map": {
                    "users": None,
                    "scales": None,
                    "vitals": None,
                    "education": None,
                }
            },
        )

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def override_get_async_session():
            async with session_factory() as session:
                yield session

        # Создаём тестового пользователя
        test_user = None
        async with session_factory() as session:
            user = User(
                telegram_id="12345",
                full_name="Test User",
                consent_personal_data=True,
                consent_bot_use=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            test_user = user

        async def override_get_current_user():
            return test_user

        app = FastAPI()
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.include_router(scales_router, prefix="/api/v1/scales")

        client = TestClient(app)
        payload = {
            "scale_id": "TOBOL",
            "answers": [
                {"question_id": "I_7", "value": 1},
                {"question_id": "III_10", "value": 1},
                {"question_id": "V_1", "value": 1},
            ],
        }
        response = client.post("/api/v1/scales/TOBOL/submit", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["total_score"] == 12
        assert "summary" in data["result"]

        async with session_factory() as session:
            res = await session.execute(select(ScaleResult))
            saved = res.scalars().first()
            assert saved is not None
            assert saved.scale_code == "TOBOL"
            assert (saved.result_json or {}).get("total_score") == 12

        await engine.dispose()

    asyncio.run(runner())

