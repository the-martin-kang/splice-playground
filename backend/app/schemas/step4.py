from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common frontend helpers
# ---------------------------------------------------------------------------

class Step4MolstarTargetPublic(BaseModel):
    structure_asset_id: Optional[str] = None
    provider: Optional[str] = None
    source_db: Optional[str] = None
    source_id: Optional[str] = None
    source_chain_id: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    format: Optional[str] = None


class Step4CapabilitiesPublic(BaseModel):
    normal_structure_ready: bool = False
    user_track_available: bool = False
    structure_prediction_enabled: bool = False
    create_job_endpoint_enabled: bool = False
    prediction_mode: Literal["disabled", "job_queue"] = "disabled"
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Baseline STEP4 (normal track)
# ---------------------------------------------------------------------------

class Step4StructureAssetPublic(BaseModel):
    structure_asset_id: str
    provider: str
    source_db: str
    source_id: str
    source_chain_id: Optional[str] = None
    structure_kind: str
    title: Optional[str] = None
    method: Optional[str] = None
    resolution_angstrom: Optional[float] = None
    sequence_identity: Optional[float] = None
    mapped_coverage: Optional[float] = None
    mapped_start: Optional[int] = None
    mapped_end: Optional[int] = None
    mean_plddt: Optional[float] = None
    file_format: str
    viewer_format: Optional[str] = None
    is_default: bool = False
    validation_status: str
    signed_url: Optional[str] = None
    signed_url_expires_in: Optional[int] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)
    validation_report: Dict[str, Any] = Field(default_factory=dict)


class Step4BaselineProteinPublic(BaseModel):
    protein_reference_id: str
    gene_id: str
    transcript_id: str
    transcript_source: str
    transcript_kind: str
    refseq_transcript_id: Optional[str] = None
    refseq_protein_id: Optional[str] = None
    ensembl_gene_id: Optional[str] = None
    ensembl_transcript_id: Optional[str] = None
    ensembl_protein_id: Optional[str] = None
    uniprot_accession: Optional[str] = None
    uniprot_isoform_id: Optional[str] = None
    uniprot_entry_name: Optional[str] = None
    uniprot_reviewed: Optional[bool] = None
    protein_length: int
    cds_start_cdna_1: Optional[int] = None
    cds_end_cdna_1: Optional[int] = None
    validation_status: str
    validation_report: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)

    canonical_mrna_seq: Optional[str] = None
    cds_seq: Optional[str] = None
    protein_seq: Optional[str] = None


class Step4BaselineResponse(BaseModel):
    disease_id: Optional[str] = None
    state_id: Optional[str] = None
    gene_id: str
    gene_symbol: Optional[str] = None

    baseline_protein: Step4BaselineProteinPublic
    structures: List[Step4StructureAssetPublic] = Field(default_factory=list)

    default_structure_asset_id: Optional[str] = None
    default_structure: Optional[Step4StructureAssetPublic] = None
    molstar_default: Optional[Step4MolstarTargetPublic] = None
    capabilities: Step4CapabilitiesPublic = Field(default_factory=Step4CapabilitiesPublic)
    ready_for_frontend: bool = False
    notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stateful STEP4 (two-track response)
# ---------------------------------------------------------------------------

class Step4TranscriptBlockPublic(BaseModel):
    block_id: str
    block_kind: Literal["canonical_exon", "pseudo_exon", "boundary_shift"]
    label: str
    gene_start_idx: int = Field(ge=0)
    gene_end_idx: int = Field(ge=0)
    length: int = Field(gt=0)
    canonical_exon_number: Optional[int] = Field(default=None, ge=1)
    cdna_start_1: Optional[int] = Field(default=None, ge=1)
    cdna_end_1: Optional[int] = Field(default=None, ge=1)
    notes: List[str] = Field(default_factory=list)


class Step4PredictedTranscriptPublic(BaseModel):
    primary_event_type: str
    primary_subtype: Optional[str] = None
    blocks: List[Step4TranscriptBlockPublic] = Field(default_factory=list)
    included_exon_numbers: List[int] = Field(default_factory=list)
    excluded_exon_numbers: List[int] = Field(default_factory=list)
    inserted_block_count: int = 0
    warnings: List[str] = Field(default_factory=list)


class Step4TranslationSanityPublic(BaseModel):
    translation_ok: bool
    reason: Optional[str] = None

    baseline_cds_start_cdna_1: Optional[int] = None
    baseline_cds_end_cdna_1: Optional[int] = None
    user_cds_start_cdna_1: Optional[int] = None
    user_cds_end_cdna_1: Optional[int] = None

    start_codon_preserved: bool = False
    start_codon_triplet: Optional[str] = None
    stop_codon_found: bool = False
    stop_codon_triplet: Optional[str] = None
    multiple_of_three: bool = False
    internal_stop_positions_aa: List[int] = Field(default_factory=list)

    frameshift_likely: Optional[bool] = None
    premature_stop_likely: Optional[bool] = None

    protein_length: int = 0
    cds_length_nt: int = 0
    notes: List[str] = Field(default_factory=list)


class Step4SequenceComparisonPublic(BaseModel):
    same_as_normal: bool
    normal_protein_length: int
    user_protein_length: int
    length_delta_aa: int
    first_mismatch_aa_1: Optional[int] = None
    normalized_edit_similarity: float = Field(ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)


class Step4JobAssetPublic(BaseModel):
    kind: Literal["structure", "pae", "scores", "logs", "input", "other"]
    file_format: str
    viewer_format: Optional[str] = None
    bucket: str
    path: str
    name: Optional[str] = None
    is_default: bool = False
    signed_url: Optional[str] = None
    signed_url_expires_in: Optional[int] = None


class Step4StructureComparisonPublic(BaseModel):
    method: Optional[str] = None
    tm_score_1: Optional[float] = None
    tm_score_2: Optional[float] = None
    rmsd: Optional[float] = None
    aligned_length: Optional[int] = None
    raw_text_excerpt: Optional[str] = None


class Step4StructureJobPublic(BaseModel):
    job_id: str
    state_id: str
    provider: str
    status: str
    external_job_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    user_protein_sha256: Optional[str] = None
    user_protein_length: Optional[int] = None
    reused_baseline_structure: bool = False

    assets: List[Step4JobAssetPublic] = Field(default_factory=list)
    default_structure_asset: Optional[Step4JobAssetPublic] = None
    molstar_default: Optional[Step4MolstarTargetPublic] = None
    confidence: Dict[str, Any] = Field(default_factory=dict)
    comparison_to_normal: Dict[str, Any] = Field(default_factory=dict)
    structure_comparison: Optional[Step4StructureComparisonPublic] = None
    result_payload: Dict[str, Any] = Field(default_factory=dict)


class Step4NormalTrackPublic(BaseModel):
    baseline_protein: Step4BaselineProteinPublic
    structures: List[Step4StructureAssetPublic] = Field(default_factory=list)
    default_structure_asset_id: Optional[str] = None
    default_structure: Optional[Step4StructureAssetPublic] = None
    molstar_default: Optional[Step4MolstarTargetPublic] = None


class Step4UserTrackPublic(BaseModel):
    state_id: str
    representative_snv_applied: bool = False
    state_lineage: List[str] = Field(default_factory=list)
    effective_edits: List[Dict[str, Any]] = Field(default_factory=list)

    predicted_transcript: Step4PredictedTranscriptPublic
    translation_sanity: Step4TranslationSanityPublic
    comparison_to_normal: Step4SequenceComparisonPublic

    protein_seq: Optional[str] = None
    cds_seq: Optional[str] = None
    cdna_seq: Optional[str] = None

    structure_prediction_enabled: bool = False
    structure_prediction_message: Optional[str] = None
    can_reuse_normal_structure: bool = False
    recommended_structure_strategy: Literal["reuse_baseline", "predict_user_structure"]

    latest_structure_job: Optional[Step4StructureJobPublic] = None
    structure_jobs: List[Step4StructureJobPublic] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class Step4StateResponse(BaseModel):
    disease_id: str
    state_id: str
    gene_id: str
    gene_symbol: Optional[str] = None

    normal_track: Step4NormalTrackPublic
    user_track: Step4UserTrackPublic
    capabilities: Step4CapabilitiesPublic = Field(default_factory=Step4CapabilitiesPublic)

    ready_for_frontend: bool = False
    notes: List[str] = Field(default_factory=list)


class CreateStep4StructureJobRequest(BaseModel):
    provider: Literal["colabfold"] = "colabfold"
    force: bool = False
    reuse_if_identical: bool = True


class Step4StructureJobCreateResponse(BaseModel):
    created: bool
    reused_baseline_structure: bool = False
    message: str
    job: Optional[Step4StructureJobPublic] = None
    user_track: Optional[Step4UserTrackPublic] = None
