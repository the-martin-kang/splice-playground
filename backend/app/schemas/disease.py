# app/schemas/disease.py
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from app.schemas.common import Coordinate, Constraints, SchemaBase, UIHints
from app.schemas.gene import Gene
from app.schemas.region import RegionBase, RegionContext


class DiseasePublic(SchemaBase):
    disease_id: str
    disease_name: str
    description: Optional[str] = None

    # Step1 list에서는 내려주고, Step2 payload에서는 없어도 되게 Optional로
    gene_id: Optional[str] = None

    # DB 저장값: "STEP1_image/CFTR.png"
    image_path: Optional[str] = None

    # B 방식: FastAPI가 만든 signed url
    image_url: Optional[str] = None
    image_expires_in: Optional[int] = None


class DiseaseListResponse(SchemaBase):
    items: List[DiseasePublic]
    count: int


class SpliceAlteringSNV(SchemaBase):
    snv_id: Optional[str] = None

    pos_gene0: int = Field(..., ge=0)
    ref: str = Field(..., min_length=1, max_length=1)
    alt: str = Field(..., min_length=1, max_length=1)

    coordinate: Coordinate
    note: Optional[str] = None
    is_representative: Optional[bool] = None


class TargetWindow(SchemaBase):
    start_gene0: int = Field(..., ge=0)
    end_gene0: int = Field(..., ge=0)
    label: Optional[str] = None
    chosen_by: Optional[str] = None
    note: Optional[str] = None


class Step2Target(SchemaBase):
    window: TargetWindow
    focus_region: RegionBase
    context_regions: List[RegionContext]
    constraints: Constraints


class Step2PayloadResponse(SchemaBase):
    """
    STEP2-1 응답 전체 payload
    """
    disease: DiseasePublic
    gene: Gene
    splice_altering_snv: SpliceAlteringSNV
    target: Step2Target
    ui_hints: UIHints
