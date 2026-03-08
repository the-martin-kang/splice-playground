from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from app.schemas.splicing import PredictSplicingRequest, SplicingPredictionResponse
from app.services.splicing_service import predict_splicing_for_state


router = APIRouter(
    prefix="/states",
    tags=["splicing"],
)


def _debug_errors() -> bool:
    return str(os.getenv("DEBUG_ERRORS", "")).strip().lower() in {"1", "true", "yes", "y"}


@router.post("/{state_id}/splicing", response_model=SplicingPredictionResponse)
def predict_splicing_for_state_id(
    state_id: str,
    req: PredictSplicingRequest = PredictSplicingRequest(),
) -> SplicingPredictionResponse:
    """STEP3: state-based splicing prediction.

    Returns model probabilities for the *7-region target span* (focus ±3 regions),
    using ±flank context on both sides (SpliceAI-10k style).
    """
    dbg = _debug_errors()

    try:
        return predict_splicing_for_state(state_id, req)

    except ValueError as e:
        # user input / known validation errors
        raise HTTPException(status_code=400, detail=str(e)) from e

    except FileNotFoundError as e:
        # common AWS deploy issue: model .pt missing due to .dockerignore
        raise HTTPException(status_code=500, detail=str(e) if dbg else "Model checkpoint missing") from e

    except RuntimeError as e:
        # Torch / device / inference runtime issues
        msg = str(e)
        low = msg.lower()
        if "mps" in low:
            msg = msg + " (hint: set SPLICEAI_DEVICE=cpu on AWS/Linux)"
        if "cuda" in low and "available" in low:
            msg = msg + " (hint: set SPLICEAI_DEVICE=cpu on AWS unless using GPU build)"
        raise HTTPException(status_code=500, detail=msg if dbg else "SpliceAI inference runtime error") from e

    except Exception as e:
        # unexpected
        detail = f"{type(e).__name__}: {e}" if dbg else "Internal Server Error"
        raise HTTPException(status_code=500, detail=detail) from e
