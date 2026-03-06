from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.cors import setup_cors
from app.core.errors import register_exception_handlers
from app.db.supabase_client import get_supabase_client

logger = logging.getLogger("app")


def create_app() -> FastAPI:
    settings = get_settings()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

    setup_cors(app)
    register_exception_handlers(app)

    # API routes
    app.include_router(api_router, prefix=settings.API_PREFIX)

    @app.get("/", tags=["system"])
    def root():
        return {"ok": True, "name": settings.APP_NAME, "version": settings.APP_VERSION}

    @app.get("/healthz", tags=["system"])
    def healthz():
        return {"ok": True}

    @app.on_event("startup")
    def startup_check():
        # Fail fast if Supabase is misconfigured.
        sb = get_supabase_client()
        try:
            sb.table("disease").select("disease_id").limit(1).execute()
            logger.info("Supabase startup check: OK")
        except Exception as e:
            logger.exception("Supabase startup check: FAILED")
            raise

    return app


app = create_app()
