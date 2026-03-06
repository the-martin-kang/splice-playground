from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import diseases, states, splicing

api_router = APIRouter()

api_router.include_router(diseases.router)
api_router.include_router(states.router)
api_router.include_router(splicing.router)
