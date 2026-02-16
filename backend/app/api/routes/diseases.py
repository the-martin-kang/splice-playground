# app/api/routes/diseases.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase_client import DBNotFoundError, DBQueryError
from app.schemas.disease import DiseaseListResponse, Step2PayloadResponse
from app.services.disease_service import DiseaseService

router = APIRouter(prefix="/diseases", tags=["diseases"])


@router.get("", response_model=DiseaseListResponse)
def list_diseases(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> DiseaseListResponse:
    """
    STEP1: 질병 카드 리스트
    """
    try:
        raw = DiseaseService.list_diseases(limit=limit, offset=offset)
        return DiseaseListResponse.model_validate(raw)
    except DBQueryError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{disease_id}", response_model=Step2PayloadResponse)
def get_disease_step2_payload(
    disease_id: str,
    include_sequence: bool = Query(True, description="Step2 DNA 편집을 위해 region.sequence 포함 여부"),
) -> Step2PayloadResponse:
    """
    STEP2-1: 특정 disease_id에 대한 Step2 화면 구성 payload
    """
    try:
        raw = DiseaseService.get_step2_payload(disease_id=disease_id, include_sequence=include_sequence)
        return Step2PayloadResponse.model_validate(raw)
    except DBNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DBQueryError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
