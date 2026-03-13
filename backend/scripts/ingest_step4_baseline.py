#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.config import get_settings
from app.services.protein_translation import sha256_text
from app.services.step4_sources import (
    UniProtClient,
    alphafold_structure_candidates,
    build_sequence_validation_report,
    choose_default_structure,
    download_rcsb_cif,
    download_url_bytes,
    mean_plddt_from_pdb_bytes,
    pdbe_structure_candidates,
    resolve_transcript_reference_bundle,
    structure_download_filename,
    summarize_validation_status,
)


PASS_STATUSES = {"pass_strict", "pass_refseq_only", "pass_transcript_only"}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)



def _get_target_gene_rows(args: argparse.Namespace) -> List[Dict[str, Any]]:
    from app.db.repositories import disease_repo, gene_repo
    from app.services.gene_context import resolve_single_gene_id_for_disease
    gene_ids: List[str] = []
    if args.gene_id:
        gene_ids.extend(args.gene_id)
    if args.disease_id:
        for did in args.disease_id:
            drow = disease_repo.get_disease(did)
            if not drow:
                raise ValueError(f"disease not found: {did}")
            gene_ids.append(resolve_single_gene_id_for_disease(did, drow))

    if not gene_ids:
        # Default: visible disease cases only, deduplicated by gene_id.
        rows, _ = disease_repo.list_diseases(limit=1000, offset=0, include_hidden=bool(args.include_hidden))
        for drow in rows:
            try:
                gene_ids.append(resolve_single_gene_id_for_disease(str(drow["disease_id"]), drow))
            except Exception:
                continue

    deduped: List[str] = []
    seen = set()
    for gid in gene_ids:
        if gid not in seen:
            deduped.append(gid)
            seen.add(gid)

    out: List[Dict[str, Any]] = []
    for gid in deduped:
        grow = gene_repo.get_gene(gid)
        if not grow:
            raise ValueError(f"gene not found: {gid}")
        out.append(grow)
    return out



def _fetch_uniprot_metadata(accession: Optional[str]) -> Tuple[Optional[str], Optional[bool], Dict[str, Any]]:
    if not accession:
        return None, None, {}
    try:
        data = UniProtClient().entry_json(accession)
        entry_name = (
            data.get("uniProtkbId")
            or data.get("entryName")
            or data.get("primaryAccession")
            or accession
        )
        reviewed = "Swiss-Prot" in str(data.get("entryType") or "")
        return str(entry_name), bool(reviewed), {"entryType": data.get("entryType"), "primaryAccession": data.get("primaryAccession")}
    except Exception as e:
        return None, None, {"uniprot_fetch_error": str(e)}



def _final_validation_status(external_status: str, db_report: Dict[str, Any]) -> str:
    if external_status not in PASS_STATUSES:
        return external_status
    if not bool(db_report.get("ok")):
        return "review_required"
    return external_status



def _build_protein_reference_payload(gene_row: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.step4_validation import validate_db_regions_against_reference
    bundle = resolve_transcript_reference_bundle(gene_row)
    external_report = build_sequence_validation_report(bundle)
    db_report = validate_db_regions_against_reference(
        gene_id=str(gene_row["gene_id"]),
        canonical_mrna_seq=bundle.cdna_seq,
        cds_start_cdna_1=bundle.cds_start_cdna_1,
        cds_end_cdna_1=bundle.cds_end_cdna_1,
        expected_cds_seq=bundle.cds_seq,
        expected_protein_seq=bundle.protein_seq,
    )
    validation_status = _final_validation_status(summarize_validation_status(external_report), db_report)
    entry_name, reviewed, extra_uniprot_meta = _fetch_uniprot_metadata(bundle.uniprot_accession)

    validation_report = {
        "external_sequence_validation": external_report,
        "db_region_validation": db_report,
    }
    provenance = {
        **bundle.provenance,
        "uniprot_metadata": extra_uniprot_meta,
        "pipeline": {
            "name": "step4_baseline_ingest",
            "source_priority": [
                "MANE/Ensembl transcript as transcript authority",
                "RefSeq protein cross-check",
                "UniProt reviewed protein cross-check",
                "PDBe/RCSB experimental structures first",
                "AlphaFoldDB predicted structure fallback",
            ],
        },
    }

    return {
        "payload": {
            "gene_id": str(gene_row["gene_id"]),
            "transcript_id": bundle.ensembl_transcript_id,
            "transcript_source": bundle.canonical_source or bundle.transcript_kind,
            "transcript_kind": bundle.transcript_kind,
            "refseq_transcript_id": bundle.refseq_transcript_id,
            "refseq_protein_id": bundle.refseq_protein_id,
            "ensembl_gene_id": bundle.ensembl_gene_id,
            "ensembl_transcript_id": bundle.ensembl_transcript_id,
            "ensembl_protein_id": bundle.ensembl_protein_id,
            "uniprot_accession": bundle.uniprot_accession,
            "uniprot_isoform_id": None,
            "uniprot_entry_name": entry_name,
            "uniprot_reviewed": reviewed,
            "canonical_mrna_seq": bundle.cdna_seq,
            "cds_seq": bundle.cds_seq,
            "cds_start_cdna_1": bundle.cds_start_cdna_1,
            "cds_end_cdna_1": bundle.cds_end_cdna_1,
            "protein_seq": bundle.protein_seq,
            "protein_length": len(bundle.protein_seq),
            "canonical_mrna_sha256": sha256_text(bundle.cdna_seq),
            "cds_sha256": sha256_text(bundle.cds_seq),
            "protein_sha256": sha256_text(bundle.protein_seq),
            "validation_status": validation_status,
            "validation_report": validation_report,
            "provenance": provenance,
        },
        "bundle": bundle,
        "external_report": external_report,
        "db_report": db_report,
        "validation_status": validation_status,
    }



def _upload_experimental_structures(
    *,
    protein_reference_id: str,
    gene_id: str,
    protein_length: int,
    uniprot_accession: str,
    top_n: int,
    default_source_key: Tuple[str, str, str],
    dry_run: bool,
) -> List[Dict[str, Any]]:
    from app.services.storage_service import upload_bytes_to_storage
    candidates = pdbe_structure_candidates(uniprot_accession)[: max(0, int(top_n))]
    uploaded: List[Dict[str, Any]] = []
    bucket = get_settings().STEP4_STRUCTURE_BUCKET

    for cand in candidates:
        source_key = (str(cand.get("provider") or ""), str(cand.get("source_id") or ""), str(cand.get("source_chain_id") or ""))
        filename = structure_download_filename(cand, "cif")
        object_path = f"{gene_id}/experimental/{filename}"
        validation_report = {
            "auto_ingest": True,
            "mapped_coverage": cand.get("mapped_coverage"),
            "sequence_identity": cand.get("sequence_identity"),
            "uniprot_accession": uniprot_accession,
        }
        file_sha256 = None
        if dry_run:
            data_len = None
        else:
            cif_bytes = download_rcsb_cif(str(cand["source_id"]))
            upload_bytes_to_storage(
                bucket=bucket,
                object_path=object_path,
                data=cif_bytes,
                content_type="text/plain",
                upsert=True,
            )
            data_len = len(cif_bytes)
            file_sha256 = sha256_text(cif_bytes.decode("utf-8", errors="replace"))
            validation_report["downloaded_bytes"] = data_len
            validation_report["file_sha256"] = file_sha256

        payload = {
            "protein_reference_id": protein_reference_id,
            "provider": str(cand.get("provider") or "pdbe_best_structures"),
            "source_db": "PDB",
            "source_id": str(cand.get("source_id") or ""),
            "source_chain_id": str(cand.get("source_chain_id") or ""),
            "structure_kind": "experimental",
            "title": cand.get("title") or f"PDB {cand.get('source_id')}",
            "method": cand.get("method"),
            "resolution_angstrom": cand.get("resolution_angstrom"),
            "sequence_identity": cand.get("sequence_identity"),
            "mapped_coverage": cand.get("mapped_coverage"),
            "mapped_start": cand.get("mapped_start"),
            "mapped_end": cand.get("mapped_end"),
            "mean_plddt": None,
            "storage_bucket": bucket,
            "storage_path": object_path,
            "file_format": "cif",
            "is_default": source_key == default_source_key,
            "validation_status": "pass_auto",
            "validation_report": validation_report,
            "provenance": {"source_payload": cand.get("source_payload") or {}, "file_sha256": file_sha256},
        }
        uploaded.append(payload)
    return uploaded



def _upload_predicted_structure(
    *,
    protein_reference_id: str,
    gene_id: str,
    protein_length: int,
    uniprot_accession: str,
    default_source_key: Tuple[str, str, str],
    dry_run: bool,
) -> List[Dict[str, Any]]:
    from app.services.storage_service import upload_bytes_to_storage
    candidates = alphafold_structure_candidates(uniprot_accession)
    if not candidates:
        return []
    cand = candidates[0]
    if not cand.get("cif_url"):
        return []

    mapped_start = int(cand.get("mapped_start") or 1)
    mapped_end = int(cand.get("mapped_end") or protein_length)
    mapped_coverage = round(max(0, mapped_end - mapped_start + 1) / max(1, protein_length), 6)

    mean_plddt = None
    validation_report: Dict[str, Any] = {
        "auto_ingest": True,
        "mapped_start": mapped_start,
        "mapped_end": mapped_end,
        "mapped_coverage": mapped_coverage,
        "uniprot_accession": uniprot_accession,
    }

    filename = structure_download_filename(cand, "cif")
    object_path = f"{gene_id}/predicted/{filename}"
    bucket = get_settings().STEP4_STRUCTURE_BUCKET

    file_sha256 = None
    if not dry_run:
        cif_bytes = download_url_bytes(str(cand["cif_url"]))
        upload_bytes_to_storage(
            bucket=bucket,
            object_path=object_path,
            data=cif_bytes,
            content_type="text/plain",
            upsert=True,
        )
        validation_report["downloaded_bytes"] = len(cif_bytes)
        file_sha256 = sha256_text(cif_bytes.decode("utf-8", errors="replace"))
        validation_report["file_sha256"] = file_sha256
        if cand.get("pdb_url"):
            try:
                pdb_bytes = download_url_bytes(str(cand["pdb_url"]))
                mean_plddt = mean_plddt_from_pdb_bytes(pdb_bytes)
            except Exception as e:
                validation_report["pdb_plddt_parse_error"] = str(e)

    source_key = (str(cand.get("provider") or ""), str(cand.get("source_id") or ""), str(cand.get("source_chain_id") or ""))
    return [
        {
            "protein_reference_id": protein_reference_id,
            "provider": str(cand.get("provider") or "alphafold_db"),
            "source_db": "AlphaFoldDB",
            "source_id": str(cand.get("source_id") or ""),
            "source_chain_id": str(cand.get("source_chain_id") or ""),
            "structure_kind": "predicted",
            "title": cand.get("title") or f"AlphaFold prediction for {uniprot_accession}",
            "method": "AlphaFoldDB",
            "resolution_angstrom": None,
            "sequence_identity": 1.0,
            "mapped_coverage": mapped_coverage,
            "mapped_start": mapped_start,
            "mapped_end": mapped_end,
            "mean_plddt": mean_plddt,
            "storage_bucket": bucket,
            "storage_path": object_path,
            "file_format": "cif",
            "is_default": source_key == default_source_key,
            "validation_status": "pass_auto" if mean_plddt is None or mean_plddt >= 0 else "review_required",
            "validation_report": validation_report,
            "provenance": {"source_payload": cand.get("source_payload") or {}, "cif_url": cand.get("cif_url"), "pdb_url": cand.get("pdb_url"), "file_sha256": file_sha256},
        }
    ]



def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest STEP4 baseline protein sequences and structure assets into Supabase")
    ap.add_argument("--gene-id", action="append", help="gene_id from your gene table (repeatable)")
    ap.add_argument("--disease-id", action="append", help="disease_id to resolve to gene_id (repeatable)")
    ap.add_argument("--include-hidden", action="store_true", help="When auto-discovering targets, include hidden disease cases")
    ap.add_argument("--top-pdb", type=int, default=3, help="How many PDBe best experimental structures to keep")
    ap.add_argument("--skip-structures", action="store_true", help="Only ingest sequence/protein metadata, skip structure files")
    ap.add_argument("--skip-alphafold", action="store_true", help="Do not download AlphaFoldDB predicted structures")
    ap.add_argument("--dry-run", action="store_true", help="Resolve and validate everything, but do not write to Supabase")
    args = ap.parse_args()

    from app.db.repositories.step4_baseline_repo import clear_default_structure_flags, upsert_protein_reference, upsert_structure_asset

    targets = _get_target_gene_rows(args)
    summaries: List[Dict[str, Any]] = []

    for grow in targets:
        gene_id = str(grow["gene_id"])
        gene_symbol = str(grow.get("gene_symbol") or gene_id)
        print(f"[STEP4] Processing {gene_id} ({gene_symbol}) ...")
        built = _build_protein_reference_payload(grow)
        payload = built["payload"]

        protein_reference_id = "DRY_RUN"
        if not args.dry_run:
            row = upsert_protein_reference(payload)
            protein_reference_id = str(row["protein_reference_id"])

        validation_status = str(built["validation_status"])
        structure_assets_written = 0
        structure_notes: List[str] = []

        external_cross = (((built.get("external_report") or {}).get("cross_source") or {}))
        uniprot_exact = bool((external_cross.get("uniprot_vs_cds_translation") or {}).get("match"))
        uniprot_accession = payload.get("uniprot_accession")
        protein_length = int(payload.get("protein_length") or 0)

        if not args.skip_structures:
            if uniprot_accession and uniprot_exact and validation_status in PASS_STATUSES:
                exp_candidates = pdbe_structure_candidates(str(uniprot_accession))[: max(0, int(args.top_pdb))]
                pred_candidates = [] if args.skip_alphafold else alphafold_structure_candidates(str(uniprot_accession))
                all_candidates = exp_candidates + pred_candidates
                default_candidate = choose_default_structure(all_candidates)
                default_key = (
                    str(default_candidate.get("provider") or "") if default_candidate else "",
                    str(default_candidate.get("source_id") or "") if default_candidate else "",
                    str(default_candidate.get("source_chain_id") or "") if default_candidate else "",
                )

                structure_payloads: List[Dict[str, Any]] = []
                structure_payloads.extend(
                    _upload_experimental_structures(
                        protein_reference_id=protein_reference_id,
                        gene_id=gene_id,
                        protein_length=protein_length,
                        uniprot_accession=str(uniprot_accession),
                        top_n=args.top_pdb,
                        default_source_key=default_key,
                        dry_run=bool(args.dry_run),
                    )
                )
                if not args.skip_alphafold:
                    structure_payloads.extend(
                        _upload_predicted_structure(
                            protein_reference_id=protein_reference_id,
                            gene_id=gene_id,
                            protein_length=protein_length,
                            uniprot_accession=str(uniprot_accession),
                            default_source_key=default_key,
                            dry_run=bool(args.dry_run),
                        )
                    )

                if structure_payloads and not args.dry_run:
                    clear_default_structure_flags(protein_reference_id)
                    for sp in structure_payloads:
                        upsert_structure_asset(sp)
                    structure_assets_written = len(structure_payloads)
                elif structure_payloads:
                    structure_assets_written = len(structure_payloads)
                else:
                    structure_notes.append("No structure candidate passed automated selection.")
            else:
                if not uniprot_accession:
                    structure_notes.append("No UniProt accession resolved; skipping automated structure ingest.")
                elif not uniprot_exact:
                    structure_notes.append("UniProt sequence does not exactly match translated canonical CDS; skipping automated structure ingest.")
                else:
                    structure_notes.append(f"Validation status is {validation_status}; skipping automated structure ingest.")

        summary = {
            "gene_id": gene_id,
            "gene_symbol": gene_symbol,
            "protein_reference_id": protein_reference_id,
            "validation_status": validation_status,
            "uniprot_accession": uniprot_accession,
            "structure_assets_written": structure_assets_written,
            "structure_notes": structure_notes,
            "db_region_ok": bool((built.get("db_report") or {}).get("ok")),
        }
        summaries.append(summary)
        print(_json(summary))

    print("\n[STEP4] Done. Summary:")
    print(_json(summaries))


if __name__ == "__main__":
    main()
