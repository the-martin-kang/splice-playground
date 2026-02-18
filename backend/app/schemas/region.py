# app/schemas/region.py
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, model_validator

from app.schemas.common import SchemaBase


class RegionBase(SchemaBase):
    region_id: str
    region_type: Literal["exon", "intron"]
    region_number: int = Field(..., gt=0)

    gene_start_idx: int = Field(..., ge=0)
    gene_end_idx: int = Field(..., ge=0)

    length: int = Field(..., gt=0)

    # Step2에서 필요할 때만 내려주므로 Optional
    sequence: Optional[str] = None

    @model_validator(mode="after")
    def _check_bounds(self):
        if self.gene_end_idx < self.gene_start_idx:
            raise ValueError("gene_end_idx must be >= gene_start_idx")
        return self


class RegionContext(RegionBase):
    """
    Step2 context_regions용.
    focus_region 대비 상대 위치(-2..+2)를 담는다.
    """
    rel: int = Field(..., description="relative index from focus region (e.g. -2..+2)")

# app/schemas/region.py
from pydantic import BaseModel


class RegionDetailResponse(BaseModel):
    disease_id: str
    gene_id: str
    region: "RegionBase"  # RegionBase는 기존에 있는 모델 사용
