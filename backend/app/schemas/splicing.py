from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, conint, constr


# -------------------------
# Request models
# -------------------------

class Edit(BaseModel):
    """A single substitution edit in gene-local (gene0, 0-based) coordinates."""
    pos_gene0: conint(ge=0) = Field(..., alias="pos")  # type: ignore
    from_base: constr(min_length=1, max_length=1) = Field(..., alias="from")  # type: ignore
    to_base: constr(min_length=1, max_length=1) = Field(..., alias="to")  # type: ignore

    model_config = {"populate_by_name": True}


class PredictSplicingRequest(BaseModel):
    """STEP3 request (state-based).

    By default, we use:
      - 7 regions (radius=3)
      - 5000nt flank on each side (SpliceAI-10k style context)
    """
    region_radius: conint(ge=0, le=10) = 3  # type: ignore
    flank: conint(ge=0, le=20000) = 5000  # type: ignore

    include_disease_snv: bool = True
    strict_ref_check: bool = True

    # Optional override edits (applied after disease SNV, and after state.applied_edit)
    edits_override: Optional[List[Edit]] = None

    # Optional payload size controls
    return_target_sequence: bool = False

    model_config = {"extra": "ignore"}


# -------------------------
# Response models
# -------------------------

class RegionBrief(BaseModel):
    region_id: str
    region_type: Literal["exon", "intron"]
    region_number: conint(ge=1)  # type: ignore
    gene_start_idx: conint(ge=0)  # type: ignore
    gene_end_idx: conint(ge=0)  # type: ignore
    length: conint(gt=0)  # type: ignore


class RegionWithRel(RegionBrief):
    rel: int = Field(..., description="relative index vs focus region (focus=0)")


class SplicingPredictionResponse(BaseModel):
    state_id: str
    disease_id: str
    gene_id: str

    model_version: str = Field(..., description="e.g. spliceai10k_epoch8")

    region_radius: int
    flank: int

    # target span is the concatenation from target_regions[0].start to target_regions[-1].end (end exclusive)
    target_start_gene0: int
    target_end_gene0: int
    target_len: int

    # full model input span (includes flank)
    input_start_gene0: int
    input_end_gene0: int
    input_len: int

    snv_pos_gene0: int
    snv_ref: str
    snv_alt: str
    snv_index_in_target_0: int

    focus_region: RegionBrief
    target_regions: List[RegionWithRel]

    # probs: [3][target_len]  (class order: neither, acceptor, donor)
    prob_ref: List[List[float]]
    prob_alt: List[List[float]]

    # optional sequence for plotting/debugging (target span only)
    target_seq_ref: Optional[str] = None
    target_seq_alt: Optional[str] = None
