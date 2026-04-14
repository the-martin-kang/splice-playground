from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.repositories._helpers import as_list, first_or_none, run_with_retry, unwrap_execute_result
from app.db.supabase_client import get_supabase_client


PROTEIN_REFERENCE_SELECT_SUMMARY = (
    "protein_reference_id,gene_id,transcript_id,transcript_source,transcript_kind,"
    "refseq_transcript_id,refseq_protein_id,ensembl_gene_id,ensembl_transcript_id,"
    "ensembl_protein_id,uniprot_accession,uniprot_isoform_id,uniprot_entry_name,"
    "uniprot_reviewed,cds_start_cdna_1,cds_end_cdna_1,protein_length,"
    "validation_status,validation_report,provenance,created_at,updated_at"
)

PROTEIN_REFERENCE_SELECT_DETAIL = (
    "protein_reference_id,gene_id,transcript_id,transcript_source,transcript_kind,"
    "refseq_transcript_id,refseq_protein_id,ensembl_gene_id,ensembl_transcript_id,"
    "ensembl_protein_id,uniprot_accession,uniprot_isoform_id,uniprot_entry_name,"
    "uniprot_reviewed,canonical_mrna_seq,cds_seq,cds_start_cdna_1,cds_end_cdna_1,"
    "protein_seq,protein_length,canonical_mrna_sha256,cds_sha256,protein_sha256,"
    "validation_status,validation_report,provenance,created_at,updated_at"
)

STRUCTURE_ASSET_SELECT = (
    "structure_asset_id,protein_reference_id,provider,source_db,source_id,source_chain_id,"
    "structure_kind,title,method,resolution_angstrom,sequence_identity,mapped_coverage,"
    "mapped_start,mapped_end,mean_plddt,storage_bucket,storage_path,file_format,is_default,"
    "validation_status,validation_report,provenance,created_at,updated_at"
)


def _protein_select(include_sequences: bool) -> str:
    return PROTEIN_REFERENCE_SELECT_DETAIL if include_sequences else PROTEIN_REFERENCE_SELECT_SUMMARY


def list_protein_references_by_gene(gene_id: str, *, include_sequences: bool = True) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    q = (
        sb.table("protein_reference")
        .select(_protein_select(include_sequences))
        .eq("gene_id", gene_id)
        .order("created_at", desc=True)
    )
    res = run_with_retry(lambda: q.execute())
    data, _, _ = unwrap_execute_result(res)
    return as_list(data)


def get_protein_reference_by_id(protein_reference_id: str, *, include_sequences: bool = True) -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    q = (
        sb.table("protein_reference")
        .select(_protein_select(include_sequences))
        .eq("protein_reference_id", protein_reference_id)
        .limit(1)
    )
    res = run_with_retry(lambda: q.execute())
    data, _, _ = unwrap_execute_result(res)
    return first_or_none(data)


def list_structure_assets(protein_reference_id: str) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    q = (
        sb.table("protein_structure_asset")
        .select(STRUCTURE_ASSET_SELECT)
        .eq("protein_reference_id", protein_reference_id)
        .order("is_default", desc=True)
        .order("structure_kind")
        .order("mapped_coverage", desc=True)
    )
    res = run_with_retry(lambda: q.execute())
    data, _, _ = unwrap_execute_result(res)
    return as_list(data)


def upsert_protein_reference(payload: Dict[str, Any]) -> Dict[str, Any]:
    sb = get_supabase_client()
    payload = dict(payload)
    try:
        res = (
            sb.table("protein_reference")
            .upsert(payload, on_conflict="gene_id,transcript_id")
            .execute()
        )
    except Exception:  # noqa: BLE001
        existing = None
        gid = payload.get("gene_id")
        tid = payload.get("transcript_id")
        if gid and tid:
            rows = list_protein_references_by_gene(str(gid), include_sequences=False)
            existing = next((r for r in rows if str(r.get("transcript_id")) == str(tid)), None)
        if existing:
            res = (
                sb.table("protein_reference")
                .update(payload)
                .eq("protein_reference_id", existing["protein_reference_id"])
                .execute()
            )
        else:
            res = sb.table("protein_reference").insert(payload).execute()
    data, _, _ = unwrap_execute_result(res)
    row = first_or_none(data)
    if not row:
        rows = list_protein_references_by_gene(str(payload.get("gene_id") or ""), include_sequences=True)
        row = next((r for r in rows if str(r.get("transcript_id") or "") == str(payload.get("transcript_id") or "")), None)
    if not row:
        raise RuntimeError("Failed to upsert protein_reference")
    return row


def upsert_structure_asset(payload: Dict[str, Any]) -> Dict[str, Any]:
    sb = get_supabase_client()
    payload = dict(payload)
    payload.setdefault("source_chain_id", "")
    try:
        res = (
            sb.table("protein_structure_asset")
            .upsert(payload, on_conflict="protein_reference_id,provider,source_id,source_chain_id,file_format")
            .execute()
        )
    except Exception:  # noqa: BLE001
        existing = None
        if payload.get("protein_reference_id"):
            rows = list_structure_assets(str(payload["protein_reference_id"]))
            existing = next(
                (
                    r for r in rows
                    if str(r.get("provider") or "") == str(payload.get("provider") or "")
                    and str(r.get("source_id") or "") == str(payload.get("source_id") or "")
                    and str(r.get("source_chain_id") or "") == str(payload.get("source_chain_id") or "")
                    and str(r.get("file_format") or "") == str(payload.get("file_format") or "")
                ),
                None,
            )
        if existing:
            res = (
                sb.table("protein_structure_asset")
                .update(payload)
                .eq("structure_asset_id", existing["structure_asset_id"])
                .execute()
            )
        else:
            res = sb.table("protein_structure_asset").insert(payload).execute()
    data, _, _ = unwrap_execute_result(res)
    row = first_or_none(data)
    if row:
        return row
    if payload.get("protein_reference_id"):
        rows = list_structure_assets(str(payload["protein_reference_id"]))
        row = next(
            (
                r for r in rows
                if str(r.get("provider") or "") == str(payload.get("provider") or "")
                and str(r.get("source_id") or "") == str(payload.get("source_id") or "")
                and str(r.get("source_chain_id") or "") == str(payload.get("source_chain_id") or "")
                and str(r.get("file_format") or "") == str(payload.get("file_format") or "")
            ),
            None,
        )
        if row:
            return row
    raise RuntimeError("Failed to upsert protein_structure_asset")


def clear_default_structure_flags(protein_reference_id: str) -> None:
    sb = get_supabase_client()
    run_with_retry(lambda: sb.table("protein_structure_asset").update({"is_default": False}).eq("protein_reference_id", protein_reference_id).execute())
