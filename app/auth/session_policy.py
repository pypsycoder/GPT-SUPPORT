from __future__ import annotations

from datetime import timedelta

from app.core.config import settings

SESSION_TTL = timedelta(days=30)
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
COOKIE_PATH = "/"
COOKIE_HTTP_ONLY = True
COOKIE_SAMESITE = "lax"


def session_cookie_secure() -> bool:
    return settings.environment.lower() == "prod"
