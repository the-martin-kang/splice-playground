# app/main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.cors import setup_cors
from app.db.supabase_client import (
    DBConflictError,
    DBError,
    DBNotFoundError,
    DBQueryError,
)
from app.schemas.common import APIError, ErrorResponse

logger = logging.getLogger("app")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _error_json(
    *,
    status_code: int,
    code: str,
    message: str,
    detail: Optional[dict] = None,
) -> JSONResponse:
    body = ErrorResponse(error=APIError(code=code, message=message, detail=detail)).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def _http_code_from_status(status_code: int) -> str:
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
    if status_code == 501:
        return "NOT_IMPLEMENTED"
    if 500 <= status_code <= 599:
        return "INTERNAL_SERVER_ERROR"
    return "HTTP_ERROR"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    if settings.check_supabase_on_startup:
        try:
            from supabase import create_client

            sb = create_client(settings.supabase_url, settings.supabase_service_key)
            sb.table("disease").select("disease_id").limit(1).execute()
            logger.info("Supabase startup check: OK")
        except Exception:
            logger.exception("Supabase startup check failed")
            raise

    yield


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        lifespan=lifespan,
    )

    app.state.settings = settings
    setup_cors(app, settings)

    # -------------------------
    # Global exception handlers
    # -------------------------
    @app.exception_handler(DBNotFoundError)
    async def _handle_not_found(request: Request, exc: DBNotFoundError):
        return _error_json(status_code=404, code="NOT_FOUND", message=str(exc))

    @app.exception_handler(DBConflictError)
    async def _handle_conflict(request: Request, exc: DBConflictError):
        return _error_json(status_code=409, code="CONFLICT", message=str(exc))

    @app.exception_handler(DBQueryError)
    async def _handle_db_query(request: Request, exc: DBQueryError):
        # 개발 단계에서는 메시지를 그대로 노출해도 편함
        msg = str(exc) if settings.debug else "Database query failed"
        detail = {"debug": str(exc)} if settings.debug else None
        return _error_json(status_code=500, code="DB_ERROR", message=msg, detail=detail)

    @app.exception_handler(DBError)
    async def _handle_db_error(request: Request, exc: DBError):
        msg = str(exc) if settings.debug else "Database error"
        detail = {"debug": str(exc)} if settings.debug else None
        return _error_json(status_code=500, code="DB_ERROR", message=msg, detail=detail)

    @app.exception_handler(ValueError)
    async def _handle_value_error(request: Request, exc: ValueError):
        return _error_json(status_code=400, code="BAD_REQUEST", message=str(exc))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError):
        # FastAPI 기본 422를 우리 형식으로 감쌈
        return _error_json(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            detail={"errors": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException):
        # placeholder(501) 등 FastAPI/Starlette HTTPException도 통일
        status = int(getattr(exc, "status_code", 500) or 500)
        code = _http_code_from_status(status)

        # detail이 이미 ErrorResponse 형태면 그대로 사용
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=status, content=exc.detail)

        message = str(exc.detail) if exc.detail is not None else "HTTP error"
        return _error_json(status_code=status, code=code, message=message)

    @app.exception_handler(Exception)
    async def _handle_unknown(request: Request, exc: Exception):
        logger.exception("Unhandled exception")
        msg = str(exc) if settings.debug else "Internal server error"
        detail = {"debug": str(exc)} if settings.debug else None
        return _error_json(status_code=500, code="INTERNAL_SERVER_ERROR", message=msg, detail=detail)

    # ---- system routes ----
    @app.get("/healthz", tags=["system"])
    def healthz():
        return {"status": "ok", "env": settings.env}

    @app.get("/", tags=["system"])
    def root():
        return {"service": settings.app_name, "env": settings.env}

    # ---- API Router include ----
    from app.api.router import router as api_router

    router_prefix: Optional[str] = getattr(api_router, "prefix", None)
    if router_prefix:
        app.include_router(api_router)
    else:
        app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
