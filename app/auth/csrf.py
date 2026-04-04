from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request, status

from app.core.config import settings


CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


def csrf_protection_enabled() -> bool:
    return bool(settings.csrf_enabled)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def should_enforce_csrf(request: Request) -> bool:
    if not csrf_protection_enabled():
        return False
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    return bool(request.cookies.get("patient_session") or request.cookies.get("researcher_session"))


async def require_csrf(
    request: Request,
    csrf_cookie: Optional[str] = Cookie(None, alias=CSRF_COOKIE_NAME),
    csrf_header: Optional[str] = Header(None, alias=CSRF_HEADER_NAME),
) -> None:
    if not should_enforce_csrf(request):
        return
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )
