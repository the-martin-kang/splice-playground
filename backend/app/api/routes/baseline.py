# app/api/routes/baseline.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/baseline", tags=["step3"])


@router.get("/{gene_id}/splicing")
def get_baseline_splicing_placeholder(
    gene_id: str,
    step: str = Query("step3", description="reserved"),
    model_version: Optional[str] = Query(None, description="reserved"),
) -> Dict[str, Any]:
    """
    STEP3 placeholder
    - 나중에 baseline_result(step3)에서 읽거나,
      SpliceAI 기반 baseline 계산으로 바뀔 예정
    """
    raise HTTPException(status_code=501, detail="Step3 baseline splicing endpoint not implemented yet")
