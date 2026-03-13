from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
    ready_for_frontend: bool = False
    notes: List[str] = Field(default_factory=list)
