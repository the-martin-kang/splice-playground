#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
from typing import Any, Dict, List, Optional



def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)



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



def _pick_best_row(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        raise ValueError("No protein_reference row found")
    ranked = sorted(rows, key=lambda r: (_rank_validation_status(r.get("validation_status")), _rank_transcript_kind(r.get("transcript_kind")), str(r.get("transcript_id") or "")))
    return ranked[0]



def _resolve_gene_id(args: argparse.Namespace) -> str:
    from app.db.repositories import disease_repo, state_repo
    from app.services.gene_context import resolve_single_gene_id_for_disease
    if args.gene_id:
        return args.gene_id
    if args.disease_id:
        drow = disease_repo.get_disease(args.disease_id)
        if not drow:
            raise ValueError(f"disease not found: {args.disease_id}")
        return resolve_single_gene_id_for_disease(args.disease_id, drow)
    if args.state_id:
        srow = state_repo.get_state(args.state_id)
        if not srow:
            raise ValueError(f"state not found: {args.state_id}")
        gid = srow.get("gene_id")
        if gid:
            return str(gid)
        drow = disease_repo.get_disease(str(srow.get("disease_id") or ""))
        if not drow:
            raise ValueError(f"disease not found for state: {args.state_id}")
        return resolve_single_gene_id_for_disease(str(srow.get("disease_id") or ""), drow)
    raise ValueError("Provide one of --gene-id, --disease-id, or --state-id")



def main() -> None:
    ap = argparse.ArgumentParser(description="Validate that DB canonical mRNA translates to the stored STEP4 baseline protein")
    ap.add_argument("--gene-id")
    ap.add_argument("--disease-id")
    ap.add_argument("--state-id")
    ap.add_argument("--write-back", action="store_true", help="Write revalidation report back into protein_reference.validation_report")
    args = ap.parse_args()

    from app.db.repositories import gene_repo
    from app.db.repositories.step4_baseline_repo import list_protein_references_by_gene, upsert_protein_reference
    from app.services.step4_validation import validate_db_regions_against_reference

    gene_id = _resolve_gene_id(args)
    grow = gene_repo.get_gene(gene_id)
    if not grow:
        raise ValueError(f"gene not found: {gene_id}")

    rows = list_protein_references_by_gene(gene_id)
    row = _pick_best_row(rows)
    report = validate_db_regions_against_reference(
        gene_id=gene_id,
        canonical_mrna_seq=str(row.get("canonical_mrna_seq") or ""),
        cds_start_cdna_1=(int(row["cds_start_cdna_1"]) if row.get("cds_start_cdna_1") is not None else None),
        cds_end_cdna_1=(int(row["cds_end_cdna_1"]) if row.get("cds_end_cdna_1") is not None else None),
        expected_cds_seq=str(row.get("cds_seq") or ""),
        expected_protein_seq=str(row.get("protein_seq") or ""),
    )

    output = {
        "gene_id": gene_id,
        "gene_symbol": grow.get("gene_symbol"),
        "protein_reference_id": row.get("protein_reference_id"),
        "transcript_id": row.get("transcript_id"),
        "current_validation_status": row.get("validation_status"),
        "db_region_revalidation": report,
    }
    print(_json(output))

    if args.write_back:
        merged_report = dict(row.get("validation_report") or {})
        merged_report["db_region_revalidation"] = report
        updated = dict(row)
        updated["validation_report"] = merged_report
        if not bool(report.get("ok")):
            updated["validation_status"] = "review_required"
        upsert_protein_reference(updated)
        print("[STEP4] validation report written back.")


if __name__ == "__main__":
    main()
