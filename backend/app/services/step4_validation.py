from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.repositories import region_repo
from app.services.protein_translation import compare_sequences, normalize_nt, translate_cds



def build_canonical_mrna_from_region_rows(region_rows: List[Dict[str, Any]]) -> str:
    exons = [r for r in region_rows if str(r.get("region_type") or "").lower() == "exon"]
    exons_sorted = sorted(exons, key=lambda r: int(r.get("region_number") or 0))
    return "".join(str(r.get("sequence") or "").upper() for r in exons_sorted)



def validate_db_regions_against_reference(
    *,
    gene_id: str,
    canonical_mrna_seq: str,
    cds_start_cdna_1: Optional[int],
    cds_end_cdna_1: Optional[int],
    expected_cds_seq: str,
    expected_protein_seq: str,
) -> Dict[str, Any]:
    rows = region_repo.list_regions_by_gene(gene_id, include_sequence=True)
    db_mrna = build_canonical_mrna_from_region_rows(rows)
    ref_mrna = normalize_nt(canonical_mrna_seq)
    ref_cds = normalize_nt(expected_cds_seq)

    report: Dict[str, Any] = {
        "db_exon_count": len([r for r in rows if str(r.get("region_type") or "").lower() == "exon"]),
        "db_mrna_length": len(db_mrna),
        "reference_mrna_length": len(ref_mrna),
        "db_mrna_exact_match": db_mrna == ref_mrna,
        "cds_start_cdna_1": cds_start_cdna_1,
        "cds_end_cdna_1": cds_end_cdna_1,
    }

    if cds_start_cdna_1 is None or cds_end_cdna_1 is None:
        report["ok"] = False
        report["reason"] = "missing_cds_coordinates"
        return report

    if not db_mrna:
        report["ok"] = False
        report["reason"] = "empty_db_mrna"
        return report

    s0 = int(cds_start_cdna_1) - 1
    e1 = int(cds_end_cdna_1)
    if s0 < 0 or e1 > len(db_mrna) or s0 >= e1:
        report["ok"] = False
        report["reason"] = "invalid_cds_coordinates_for_db_mrna"
        return report

    db_cds = db_mrna[s0:e1]
    report["db_cds_length"] = len(db_cds)
    report["reference_cds_length"] = len(ref_cds)
    report["db_cds_exact_match"] = db_cds == ref_cds

    tr = translate_cds(db_cds)
    report["db_translation"] = {
        "ok": tr.ok,
        "reason": tr.reason,
        "protein_length": tr.protein_length,
        "start_codon_ok": tr.start_codon_ok,
        "terminal_stop_present": tr.terminal_stop_present,
        "internal_stop_positions_aa": tr.internal_stop_positions_aa,
    }
    report["db_translated_protein_vs_reference"] = compare_sequences(expected_protein_seq, tr.protein_seq)
    report["ok"] = bool(report["db_mrna_exact_match"] and report["db_cds_exact_match"] and tr.ok and report["db_translated_protein_vs_reference"]["match"])
    if not report["ok"] and "reason" not in report:
        report["reason"] = "db_region_sequence_mismatch"
    return report
