from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.db.repositories import disease_repo


def resolve_single_gene_id_for_disease(disease_id: str, disease_row: Dict[str, Any]) -> str:
    """Resolve the single gene_id associated with a disease.

    The preferred source is ``disease.gene_id``.
    For older environments that still use a bridge table, fall back to
    ``disease_gene`` when exactly one gene is linked.
    """
    gid = disease_row.get("gene_id")
    if gid:
        return str(gid)

    gids = disease_repo.get_gene_ids_for_disease(disease_id)
    if len(gids) == 1:
        return gids[0]
    if not gids:
        raise ValueError(f"No gene_id for disease_id={disease_id}")
    raise ValueError(f"Multiple gene_ids for disease_id={disease_id}: {gids}")


def build_gene_sequence(gene_len: int, regions: List[Dict[str, Any]]) -> str:
    """Assemble the full gene-direction sequence from region rows.

    Region coordinates are gene0, 0-based, inclusive at both ends.
    Missing / uncovered positions remain as ``N``.
    """
    seq = ["N"] * int(gene_len)
    for r in regions:
        rseq = (r.get("sequence") or "").upper()
        if not rseq:
            continue
        s = int(r.get("gene_start_idx", 0))
        e = int(r.get("gene_end_idx", 0))
        if e < s:
            continue

        expected = e - s + 1
        if len(rseq) != expected:
            usable = min(expected, len(rseq))
            rseq = rseq[:usable]
            e = s + usable - 1

        s2 = max(0, s)
        e2 = min(int(gene_len) - 1, e)
        if e2 < s2:
            continue

        offset = s2 - s
        chunk = rseq[offset : offset + (e2 - s2 + 1)]
        if not chunk:
            continue
        seq[s2 : e2 + 1] = list(chunk)
    return "".join(seq)


def find_focus_region(regions: List[Dict[str, Any]], pos_gene0: int) -> Tuple[int, Dict[str, Any]]:
    for i, r in enumerate(regions):
        s = int(r["gene_start_idx"])
        e = int(r["gene_end_idx"])
        if s <= pos_gene0 <= e:
            return i, r
    raise ValueError(f"SNV pos_gene0={pos_gene0} not covered by any region")


def pick_regions_with_shift(regions: List[Dict[str, Any]], focus_idx: int, radius: int) -> Tuple[List[Dict[str, Any]], int]:
    """Pick a centered block of regions and return (rows, start_index)."""
    k = int(2 * radius + 1)
    if k <= 0:
        return [regions[focus_idx]], focus_idx
    if len(regions) <= k:
        return regions, 0

    start = max(0, focus_idx - radius)
    if start + k > len(regions):
        start = max(0, len(regions) - k)
    return regions[start : start + k], start
