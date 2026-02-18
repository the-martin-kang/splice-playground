# app/api/routes/diseases.py
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.disease import DiseaseListResponse, Step2PayloadResponse, Window4000Response
from app.schemas.region import RegionDetailResponse
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
    include_sequence: bool = Query(True, description="Step2 DNA 편집을 위해 region.sequence 포함 여부"),
) -> Step2PayloadResponse:
    return DiseaseService.get_step2_payload(disease_id=disease_id, include_sequence=include_sequence)


@router.get("/{disease_id}/regions/{region_type}/{region_number}", response_model=RegionDetailResponse)
def get_region_by_type_number(
    disease_id: str,
    region_type: str,
    region_number: int,
    include_sequence: bool = Query(True, description="region.sequence 포함 여부"),
) -> RegionDetailResponse:
    return DiseaseService.get_region_detail(
        disease_id=disease_id,
        region_type=region_type,
        region_number=region_number,
        include_sequence=include_sequence,
    )


@router.get("/{disease_id}/window", response_model=Window4000Response)
def get_window(
    disease_id: str,
    window_size: int = Query(4000, ge=1, le=20000, description="variable window length"),
    strict_ref_check: bool = Query(True, description="센터 염기(ref) 불일치 시 에러"),
) -> Window4000Response:
    return DiseaseService.get_window_4000(
        disease_id=disease_id,
        window_size=window_size,
        strict_ref_check=strict_ref_check,
    )


@router.get("/{disease_id}/window_4000", response_model=Window4000Response, include_in_schema=False)
def get_window_4000_alias(
    disease_id: str,
    window_size: int = Query(4000, ge=1, le=20000),
    strict_ref_check: bool = Query(True),
) -> Window4000Response:
    return DiseaseService.get_window_4000(
        disease_id=disease_id,
        window_size=window_size,
        strict_ref_check=strict_ref_check,
    )
