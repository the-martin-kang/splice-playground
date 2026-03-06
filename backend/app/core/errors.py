from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app")


def _code_from_status(status_code: int) -> str:
    if status_code == 400:
        return "BAD_REQUEST"
    if status_code == 401:
        return "UNAUTHORIZED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 422:
        return "VALIDATION_ERROR"
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "HTTP_ERROR"


def error_envelope(code: str, message: str, detail: Optional[Any] = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        code = _code_from_status(exc.status_code)
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        detail = None if isinstance(exc.detail, str) else exc.detail
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(code, message, detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Keep FastAPI's information but wrap in our envelope
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "VALIDATION_ERROR",
                "Request validation error",
                detail=exc.errors(),
            ),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=error_envelope("BAD_REQUEST", str(exc), None),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_envelope("INTERNAL_ERROR", "Internal Server Error", None),
        )
