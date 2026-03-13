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

    Default behavior:
      - 7 regions (radius=3)
      - 5000nt flank on each side (SpliceAI-10k style context)
      - representative disease SNV included when seed_mode applies
      - parent_state_id lineage edits included before current state edits
    """

    region_radius: conint(ge=0, le=10) = 3  # type: ignore
    flank: conint(ge=0, le=20000) = 5000  # type: ignore

    include_disease_snv: bool = True
    include_parent_chain: bool = True
    strict_ref_check: bool = True

    # Optional override edits (applied after disease SNV, and after effective state edits)
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


class DeltaPeak(BaseModel):
    pos_gene0: int = Field(ge=0)
    index_in_target_0: int = Field(ge=0)
    delta: float = Field(ge=0.0, description="Positive delta magnitude for this event type")
    ref_prob: float = Field(ge=0.0, le=1.0)
    alt_prob: float = Field(ge=0.0, le=1.0)


class DeltaSummary(BaseModel):
    acceptor_gain: DeltaPeak
    acceptor_loss: DeltaPeak
    donor_gain: DeltaPeak
    donor_loss: DeltaPeak
    max_effect: Literal["acceptor_gain", "acceptor_loss", "donor_gain", "donor_loss", "none"]
    max_abs_delta: float = Field(ge=0.0)


class Step3SpliceSite(BaseModel):
    site_class: Literal["acceptor", "donor"]
    site_kind: Literal["canonical", "novel"]
    pos_gene0: int = Field(ge=0)
    index_in_target_0: int = Field(ge=0)

    region_type: Optional[Literal["exon", "intron"]] = None
    region_number: Optional[int] = Field(default=None, ge=1)
    linked_exon_number: Optional[int] = Field(default=None, ge=1)

    ref_prob: float = Field(ge=0.0, le=1.0)
    alt_prob: float = Field(ge=0.0, le=1.0)
    delta_gain: float = Field(ge=0.0, le=1.0)
    delta_loss: float = Field(ge=0.0, le=1.0)
    ratio_alt_over_ref: Optional[float] = Field(default=None, ge=0.0)

    motif_ref_ok: Optional[bool] = None
    motif_alt_ok: Optional[bool] = None
    distance_from_snv: int = Field(ge=0)

    related_canonical_pos_gene0: Optional[int] = Field(default=None, ge=0)
    related_canonical_exon_number: Optional[int] = Field(default=None, ge=1)
    shift_bp: Optional[int] = None

    confidence: Literal["high", "medium", "low", "none"] = "none"
    notes: List[str] = Field(default_factory=list)


class Step3SplicingEvent(BaseModel):
    event_type: Literal[
        "PSEUDO_EXON",
        "EXON_EXCLUSION",
        "BOUNDARY_SHIFT",
        "CANONICAL_STRENGTHENING",
        "COMPLEX",
        "NONE",
    ]
    subtype: Optional[str] = None
    confidence: Literal["high", "medium", "low"]
    score: float = Field(ge=0.0)
    summary: str

    acceptor_pos_gene0: Optional[int] = Field(default=None, ge=0)
    donor_pos_gene0: Optional[int] = Field(default=None, ge=0)
    canonical_acceptor_pos_gene0: Optional[int] = Field(default=None, ge=0)
    canonical_donor_pos_gene0: Optional[int] = Field(default=None, ge=0)
    size_bp: Optional[int] = Field(default=None, ge=1)

    affected_exon_numbers: List[int] = Field(default_factory=list)
    affected_intron_numbers: List[int] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Step3FrontendSummary(BaseModel):
    primary_event_type: str
    primary_subtype: Optional[str] = None
    confidence: Literal["high", "medium", "low"]
    headline: str
    interpretation_basis: str


class Step3LogicThresholds(BaseModel):
    general_spliceogenicity_delta: float = Field(ge=0.0, le=1.0)
    non_spliceogenicity_delta: float = Field(ge=0.0, le=1.0)
    pseudoexon_pair_delta: float = Field(ge=0.0, le=1.0)
    weak_site_delta: float = Field(ge=0.0, le=1.0)
    site_alt_prob_min: float = Field(ge=0.0, le=1.0)
    site_alt_prob_strong: float = Field(ge=0.0, le=1.0)
    pseudoexon_size_min_bp: int = Field(ge=1)
    pseudoexon_size_max_bp: int = Field(ge=1)
    relative_drop_ratio: float = Field(ge=0.0)
    notes: List[str] = Field(default_factory=list)


class SplicingPredictionResponse(BaseModel):
    state_id: str
    disease_id: str
    gene_id: str

    model_version: str = Field(..., description="e.g. spliceai10k_epoch8")
    class_order: List[str] = Field(default_factory=lambda: ["neither", "acceptor", "donor"])

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
    snv_ref_gene_direction: Optional[str] = None
    snv_alt_gene_direction: Optional[str] = None
    representative_snv_applied: bool = False
    snv_index_in_target_0: int

    focus_region: RegionBrief
    target_regions: List[RegionWithRel]

    # probs: [3][target_len]  (class order: neither, acceptor, donor)
    prob_ref: List[List[float]]
    prob_alt: List[List[float]]

    # effective edit metadata (parents first, then current state, then overrides)
    state_lineage: List[str] = Field(default_factory=list)
    effective_edits: List[Edit] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    delta_summary: Optional[DeltaSummary] = None

    # STEP3 interpretation (frontend-ready heuristic layer)
    canonical_sites: List[Step3SpliceSite] = Field(default_factory=list)
    novel_sites: List[Step3SpliceSite] = Field(default_factory=list)
    interpreted_events: List[Step3SplicingEvent] = Field(default_factory=list)
    frontend_summary: Optional[Step3FrontendSummary] = None
    logic_thresholds: Optional[Step3LogicThresholds] = None

    # optional sequence for plotting/debugging (target span only)
    target_seq_ref: Optional[str] = None
    target_seq_alt: Optional[str] = None
