from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.splicing import PredictSplicingRequest, SplicingPredictionResponse
from app.services.splicing_service import predict_splicing_for_state


router = APIRouter(
    prefix="/states",
    tags=["splicing"],
)


@router.post("/{state_id}/splicing", response_model=SplicingPredictionResponse)
def predict_splicing_for_state_id(state_id: str, req: PredictSplicingRequest = PredictSplicingRequest()) -> SplicingPredictionResponse:
    """STEP3: state-based splicing prediction.

    Returns model probabilities for the *7-region target span* (focus ±3 regions),
    using ±flank context on both sides (SpliceAI-10k style).
    """
    try:
        return predict_splicing_for_state(state_id, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
