from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.disease import DiseaseListResponse, Step2PayloadResponse
from app.schemas.region import RegionBase
from app.services.disease_service import (
    get_region_detail,
    get_step2_payload,
    get_window_payload,
    list_diseases,
)

router = APIRouter(prefix="/diseases", tags=["diseases"])


@router.get("", response_model=DiseaseListResponse)
def list_diseases_endpoint(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> DiseaseListResponse:
    return list_diseases(limit=limit, offset=offset)


@router.get("/{disease_id}", response_model=Step2PayloadResponse)
def get_disease_step2_payload(
    disease_id: str,
    include_sequence: bool = Query(True, description="Step2에서 region.sequence 포함 여부"),
) -> Step2PayloadResponse:
    return get_step2_payload(disease_id, include_sequence=include_sequence)


@router.get("/{disease_id}/regions/{region_type}/{region_number}", response_model=RegionBase, response_model_exclude_none=True)
def get_region_by_type_number(
    disease_id: str,
    region_type: str,
    region_number: int,
    include_sequence: bool = Query(True, description="region.sequence 포함 여부"),
) -> RegionBase:
    return get_region_detail(
        disease_id,
        region_type,
        region_number,
        include_sequence=include_sequence,
    )


@router.get("/{disease_id}/window", response_model_exclude_none=True)
def get_window(
    disease_id: str,
    window_size: int = Query(4000, ge=1, le=250000),
):
    # Returns dict for backward-compatibility (supports legacy ref_seq_4000 fields)
    return get_window_payload(disease_id, window_size=window_size)


@router.get("/{disease_id}/window_4000", include_in_schema=False, response_model_exclude_none=True)
def get_window_4000(disease_id: str):
    return get_window_payload(disease_id, window_size=4000)
