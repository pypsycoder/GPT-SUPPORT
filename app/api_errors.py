from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status


@dataclass(frozen=True)
class ApiErrorPayload:
    code: str
    message: str
    details: list[dict[str, Any]] | None = None

    def as_dict(self) -> dict[str, Any]:
        error_meta: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            error_meta["details"] = self.details

        return {
            "ok": False,
            "error": self.message,
            "error_code": self.code,
            "error_meta": error_meta,
            "message": self.message,
            "detail": self.message,
        }


def api_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    payload = ApiErrorPayload(code=code, message=message, details=details).as_dict()
    return JSONResponse(status_code=status_code, content=payload)


def _http_error_code(status_code: int) -> str:
    if status_code == status.HTTP_400_BAD_REQUEST:
        return "bad_request"
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return "unauthorized"
    if status_code == status.HTTP_403_FORBIDDEN:
        return "forbidden"
    if status_code == status.HTTP_404_NOT_FOUND:
        return "not_found"
    if status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        return "validation_error"
    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return "internal_error"
    return "http_error"


def register_api_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        _request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        if isinstance(exc.detail, str):
            message = exc.detail
            details = None
        elif isinstance(exc.detail, list):
            message = "Validation failed"
            details = exc.detail
        else:
            message = "Request failed"
            details = None

        return api_error_response(
            status_code=exc.status_code,
            code=_http_error_code(exc.status_code),
            message=message,
            details=details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = [
            {
                "loc": list(error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return api_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="Validation failed",
            details=details,
        )
