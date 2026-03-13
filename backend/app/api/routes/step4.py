from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.step4 import Step4BaselineResponse
from app.services.step4_baseline_service import (
    get_step4_baseline_for_disease,
    get_step4_baseline_for_state,
)


router = APIRouter(tags=["step4"])


@router.get("/diseases/{disease_id}/step4-baseline", response_model=Step4BaselineResponse)
def get_disease_step4_baseline(
    disease_id: str,
    include_sequences: bool = Query(False, description="Return canonical mRNA / CDS / protein sequence strings"),
) -> Step4BaselineResponse:
    return get_step4_baseline_for_disease(disease_id, include_sequences=include_sequences)


@router.get("/states/{state_id}/step4-baseline", response_model=Step4BaselineResponse)
def get_state_step4_baseline(
    state_id: str,
    include_sequences: bool = Query(False, description="Return canonical mRNA / CDS / protein sequence strings"),
) -> Step4BaselineResponse:
    return get_step4_baseline_for_state(state_id, include_sequences=include_sequences)
