# app/api/router.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.diseases import router as diseases_router
from app.api.routes.states import router as states_router

# placeholder routers (있다면 포함)
from app.api.routes.baseline import router as baseline_router
from app.api.routes.splicing import router as splicing_router
from app.api.routes.structure import router as structure_router

router = APIRouter()

@router.get("/ping", tags=["system"])
def ping():
    return {"ok": True}

# Step1/2
router.include_router(diseases_router)
router.include_router(states_router)

# Step3/4 placeholder
router.include_router(baseline_router)
router.include_router(splicing_router)
router.include_router(structure_router)
