# app/schemas/disease.py
from __future__ import annotations

from typing import Literal, Optional
from pydantic import Field, model_validator

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



class Window4000Response(SchemaBase):
    """
    Legacy name kept for backward compatibility.
    Now supports variable window_size.

    Center index rule:
      - odd  : center = window_size//2
      - even : choose the larger of the two centers => center = window_size//2
    """

    disease_id: str
    gene_id: str

    chromosome: Optional[str] = None
    strand: Literal["+", "-"]

    # SNV meta (ref/alt are stored as positive-strand bases)
    pos_gene0: int
    pos_hg38_1: Optional[int] = None
    ref: str = Field(..., min_length=1, max_length=1)
    alt: str = Field(..., min_length=1, max_length=1)

    # window
    window_size: int = Field(..., ge=1, le=20000)

    # computed center indices (0-based)
    left_center_index_0: int
    right_center_index_0: int
    center_index_0: int  # used center (always right center)
    center_index_1: int  # 1-based (= center_index_0 + 1)

    # gene0 coordinates for window bounds
    window_start_gene0: int
    window_end_gene0_exclusive: int

    gene_length: int
    left_pad: int
    right_pad: int

    expected_ref_at_center: str = Field(..., min_length=1, max_length=1)
    actual_ref_at_center: str = Field(..., min_length=1, max_length=1)
    ref_matches: bool

    # payload (legacy field names kept)
    ref_seq_4000: str
    alt_seq_4000: str

    @model_validator(mode="after")
    def _validate_lengths_and_center(self):
        if len(self.ref_seq_4000) != self.window_size:
            raise ValueError(
                f"ref_seq length mismatch: len={len(self.ref_seq_4000)} vs window_size={self.window_size}"
            )
        if len(self.alt_seq_4000) != self.window_size:
            raise ValueError(
                f"alt_seq length mismatch: len={len(self.alt_seq_4000)} vs window_size={self.window_size}"
            )

        if not (0 <= self.center_index_0 < self.window_size):
            raise ValueError("center_index_0 out of range")

        if self.center_index_1 != self.center_index_0 + 1:
            raise ValueError("center_index_1 must equal center_index_0 + 1")

        # even/odd center sanity check
        right = self.window_size // 2
        left = right if (self.window_size % 2 == 1) else (right - 1)

        if self.right_center_index_0 != right or self.left_center_index_0 != left:
            raise ValueError("center indices do not match the defined rule")
        if self.center_index_0 != right:
            raise ValueError("center_index_0 must be the right center index")

        # alt should differ only at center (best-effort check)
        if self.ref_seq_4000[: self.center_index_0] != self.alt_seq_4000[: self.center_index_0]:
            raise ValueError("alt_seq differs from ref_seq before center")
        if self.ref_seq_4000[self.center_index_0 + 1 :] != self.alt_seq_4000[self.center_index_0 + 1 :]:
            raise ValueError("alt_seq differs from ref_seq after center")

        return self
