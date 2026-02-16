# app/api/routes/splicing.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/states", tags=["step3"])


@router.post("/{state_id}/splicing")
def run_splicing_placeholder(state_id: str) -> Dict[str, Any]:
    """
    STEP3 placeholder
    - 이후 SpliceAI 실행 → user_state_result(step3, SpliceAI_vX) 저장
    """
    raise HTTPException(status_code=501, detail="Step3 splicing endpoint not implemented yet")
