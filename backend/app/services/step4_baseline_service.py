from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.db.repositories import disease_repo, gene_repo, state_repo
from app.db.repositories.step4_baseline_repo import list_protein_references_by_gene, list_structure_assets
from app.schemas.step4 import Step4BaselineProteinPublic, Step4BaselineResponse, Step4StructureAssetPublic
from app.services.gene_context import resolve_single_gene_id_for_disease
from app.services.storage_service import create_signed_storage_url


def _rank_validation_status(status: Optional[str]) -> int:
    s = str(status or "")
    order = {
        "pass_strict": 0,
        "pass_refseq_only": 1,
        "pass_transcript_only": 2,
        "review_required_uniprot_mismatch": 3,
        "review_required": 4,
    }
    return order.get(s, 99)


def _rank_transcript_kind(kind: Optional[str]) -> int:
    s = str(kind or "")
    order = {
        "MANE_Select": 0,
        "MANE_Plus_Clinical": 1,
        "Ensembl_canonical": 2,
    }
    return order.get(s, 99)


def _choose_best_protein_reference(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        raise HTTPException(status_code=404, detail="STEP4 baseline protein_reference not found for gene")
    ranked = sorted(
        rows,
        key=lambda r: (
            _rank_validation_status(r.get("validation_status")),
            _rank_transcript_kind(r.get("transcript_kind")),
            str(r.get("transcript_id") or ""),
        ),
    )
    return ranked[0]


def _protein_public(row: Dict[str, Any], *, include_sequences: bool) -> Step4BaselineProteinPublic:
    return Step4BaselineProteinPublic(
        protein_reference_id=str(row.get("protein_reference_id")),
        gene_id=str(row.get("gene_id")),
        transcript_id=str(row.get("transcript_id")),
        transcript_source=str(row.get("transcript_source") or row.get("transcript_kind") or "unknown"),
        transcript_kind=str(row.get("transcript_kind") or "unknown"),
        refseq_transcript_id=row.get("refseq_transcript_id"),
        refseq_protein_id=row.get("refseq_protein_id"),
        ensembl_gene_id=row.get("ensembl_gene_id"),
        ensembl_transcript_id=row.get("ensembl_transcript_id"),
        ensembl_protein_id=row.get("ensembl_protein_id"),
        uniprot_accession=row.get("uniprot_accession"),
        uniprot_isoform_id=row.get("uniprot_isoform_id"),
        uniprot_entry_name=row.get("uniprot_entry_name"),
        uniprot_reviewed=row.get("uniprot_reviewed"),
        protein_length=int(row.get("protein_length") or 0),
        cds_start_cdna_1=int(row["cds_start_cdna_1"]) if row.get("cds_start_cdna_1") is not None else None,
        cds_end_cdna_1=int(row["cds_end_cdna_1"]) if row.get("cds_end_cdna_1") is not None else None,
        validation_status=str(row.get("validation_status") or "unknown"),
        validation_report=row.get("validation_report") or {},
        provenance=row.get("provenance") or {},
        canonical_mrna_seq=(row.get("canonical_mrna_seq") if include_sequences else None),
        cds_seq=(row.get("cds_seq") if include_sequences else None),
        protein_seq=(row.get("protein_seq") if include_sequences else None),
    )



def _structure_public(row: Dict[str, Any]) -> Step4StructureAssetPublic:
    bucket = str(row.get("storage_bucket") or "")
    path = row.get("storage_path")
    signed_url, expires = create_signed_storage_url(bucket, path) if bucket and path else (None, None)
    return Step4StructureAssetPublic(
        structure_asset_id=str(row.get("structure_asset_id")),
        provider=str(row.get("provider") or "unknown"),
        source_db=str(row.get("source_db") or "unknown"),
        source_id=str(row.get("source_id") or ""),
        source_chain_id=(str(row.get("source_chain_id")) if row.get("source_chain_id") not in (None, "") else None),
        structure_kind=str(row.get("structure_kind") or "unknown"),
        title=row.get("title"),
        method=row.get("method"),
        resolution_angstrom=(float(row["resolution_angstrom"]) if row.get("resolution_angstrom") is not None else None),
        sequence_identity=(float(row["sequence_identity"]) if row.get("sequence_identity") is not None else None),
        mapped_coverage=(float(row["mapped_coverage"]) if row.get("mapped_coverage") is not None else None),
        mapped_start=(int(row["mapped_start"]) if row.get("mapped_start") is not None else None),
        mapped_end=(int(row["mapped_end"]) if row.get("mapped_end") is not None else None),
        mean_plddt=(float(row["mean_plddt"]) if row.get("mean_plddt") is not None else None),
        file_format=str(row.get("file_format") or "cif"),
        is_default=bool(row.get("is_default")),
        validation_status=str(row.get("validation_status") or "unknown"),
        signed_url=signed_url,
        signed_url_expires_in=expires,
        provenance=row.get("provenance") or {},
        validation_report=row.get("validation_report") or {},
    )



def _resolve_gene_for_disease(disease_id: str) -> Tuple[Dict[str, Any], str]:
    drow = disease_repo.get_disease(disease_id)
    if not drow:
        raise HTTPException(status_code=404, detail=f"disease not found: {disease_id}")
    gid = resolve_single_gene_id_for_disease(disease_id, drow)
    return drow, gid



def _build_step4_baseline_response(
    *,
    disease_id: Optional[str],
    state_id: Optional[str],
    gene_id: str,
    include_sequences: bool,
) -> Step4BaselineResponse:
    grow = gene_repo.get_gene(gene_id)
    if not grow:
        raise HTTPException(status_code=404, detail=f"gene not found: {gene_id}")

    protein_rows = list_protein_references_by_gene(gene_id)
    protein_row = _choose_best_protein_reference(protein_rows)
    structure_rows = list_structure_assets(str(protein_row["protein_reference_id"]))
    structures_public = [_structure_public(r) for r in structure_rows]

    default_structure_asset_id = None
    for s in structures_public:
        if s.is_default:
            default_structure_asset_id = s.structure_asset_id
            break
    if default_structure_asset_id is None and structures_public:
        default_structure_asset_id = structures_public[0].structure_asset_id

    notes: List[str] = []
    ready_for_frontend = True
    if not structures_public:
        ready_for_frontend = False
        notes.append("No structure asset uploaded yet for this baseline protein.")
    if str(protein_row.get("validation_status") or "").startswith("review_required"):
        notes.append("Sequence/provenance validation requires manual review before publication-grade use.")

    return Step4BaselineResponse(
        disease_id=disease_id,
        state_id=state_id,
        gene_id=gene_id,
        gene_symbol=str(grow.get("gene_symbol") or gene_id),
        baseline_protein=_protein_public(protein_row, include_sequences=include_sequences),
        structures=structures_public,
        default_structure_asset_id=default_structure_asset_id,
        ready_for_frontend=ready_for_frontend,
        notes=notes,
    )



def get_step4_baseline_for_disease(disease_id: str, *, include_sequences: bool = False) -> Step4BaselineResponse:
    _, gid = _resolve_gene_for_disease(disease_id)
    return _build_step4_baseline_response(
        disease_id=disease_id,
        state_id=None,
        gene_id=gid,
        include_sequences=include_sequences,
    )



def get_step4_baseline_for_state(state_id: str, *, include_sequences: bool = False) -> Step4BaselineResponse:
    srow = state_repo.get_state(state_id)
    if not srow:
        raise HTTPException(status_code=404, detail=f"state not found: {state_id}")
    disease_id = str(srow.get("disease_id") or "")
    gene_id = srow.get("gene_id")
    if not gene_id:
        _, gene_id = _resolve_gene_for_disease(disease_id)
    return _build_step4_baseline_response(
        disease_id=disease_id,
        state_id=state_id,
        gene_id=str(gene_id),
        include_sequences=include_sequences,
    )
