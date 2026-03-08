
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Coordinate, UIHints, Constraints
from app.schemas.gene import Gene
from app.schemas.region import RegionBase, RegionContext


class DiseasePublic(BaseModel):
    disease_id: str
    disease_name: str
    description: Optional[str] = None
    gene_id: Optional[str] = None

    image_path: Optional[str] = None
    image_url: Optional[str] = None
    image_expires_in: Optional[int] = None

    # service gating / metadata
    is_visible_in_service: Optional[bool] = None
    max_supported_step: Optional[int] = None
    seed_mode: Optional[str] = None
    note: Optional[str] = None


class DiseaseListResponse(BaseModel):
    items: List[DiseasePublic]
    count: int


class SpliceAlteringSNV(BaseModel):
    snv_id: Optional[str] = None
    pos_gene0: int = Field(ge=0)
    ref: str = Field(min_length=1, max_length=1)
    alt: str = Field(min_length=1, max_length=1)
    coordinate: Coordinate
    note: Optional[str] = None
    is_representative: Optional[bool] = None
    allele_coordinate_system: Optional[str] = None


class TargetWindow(BaseModel):
    start_gene0: int = Field(ge=0)
    end_gene0: int = Field(ge=0)
    label: Optional[str] = None
    chosen_by: Optional[str] = None
    note: Optional[str] = None


class Step2Target(BaseModel):
    window: TargetWindow
    focus_region: RegionBase
    context_regions: List[RegionContext]
    constraints: Constraints


class Step2PayloadResponse(BaseModel):
    disease: DiseasePublic
    gene: Gene
    splice_altering_snv: SpliceAlteringSNV
    target: Step2Target
    ui_hints: UIHints
