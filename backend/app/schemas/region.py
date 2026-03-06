from __future__ import annotations

from typing import Optional, Literal

from pydantic import BaseModel, Field


RegionType = Literal["exon", "intron"]


class RegionBase(BaseModel):
    region_id: str
    region_type: RegionType
    region_number: int = Field(gt=0)
    gene_start_idx: int = Field(ge=0)
    gene_end_idx: int = Field(ge=0)
    length: int = Field(gt=0)
    sequence: Optional[str] = None


class RegionContext(RegionBase):
    """Step2 context_regions용.

    focus_region 대비 상대 위치(-2..+2)를 담는다.
    """
    rel: int = Field(description="relative index from focus region (e.g. -2..+2)")
