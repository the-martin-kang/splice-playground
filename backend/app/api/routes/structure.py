# app/api/routes/structure.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/states", tags=["step4"])


@router.post("/{state_id}/structure")
def run_structure_placeholder(state_id: str) -> Dict[str, Any]:
    """
    STEP4 placeholder
    - 이후 structure_job 생성/큐잉 → 결과 저장/조회 흐름으로 확장
    """
    raise HTTPException(status_code=501, detail="Step4 structure endpoint not implemented yet")
