from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware.

    Use env var:
      CORS_ORIGINS=http://localhost:3000,https://example.com
    """
    settings = get_settings()
    origins = settings.CORS_ORIGINS

    if not origins:
        # If empty, we still allow localhost during development by default.
        # You can override by explicitly setting CORS_ORIGINS.
        origins = ["http://localhost:3000"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
