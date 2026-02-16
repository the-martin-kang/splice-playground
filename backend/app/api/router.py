# app/api/routes/diseases.py
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.disease import DiseaseListResponse, Step2PayloadResponse
from app.services.disease_service import DiseaseService

router = APIRouter(prefix="/diseases", tags=["diseases"])


@router.get("", response_model=DiseaseListResponse)
def list_diseases(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> DiseaseListResponse:
    return DiseaseService.list_diseases(limit=limit, offset=offset)


@router.get("/{disease_id}", response_model=Step2PayloadResponse)
def get_disease_step2_payload(
    disease_id: str,
    include_sequence: bool = Query(True, description="Step2에서 region.sequence 포함 여부"),
) -> Step2PayloadResponse:
    return DiseaseService.get_step2_payload(disease_id=disease_id, include_sequence=include_sequence)
