from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from app.db.supabase_client import get_supabase_client
from app.db.repositories._helpers import first_or_none, unwrap_execute_result

_CHR_RE = re.compile(r"(?:^|;)chr=([^;]+)")
_POS1_RE = re.compile(r"(?:^|;)pos1=([0-9]+)")


def _parse_coordinate_from_note(note: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    if not note:
        return None, None
    m1 = _CHR_RE.search(note)
    m2 = _POS1_RE.search(note)
    chrom = m1.group(1) if m1 else None
    pos1 = int(m2.group(1)) if m2 else None
    return chrom, pos1


def get_representative_snv(disease_id: str) -> Optional[Dict[str, Any]]:
    """Fetch representative splice_altering_snv for a disease.

    Preferred: is_representative=true row in splice_altering_snv
    Fallback: parse disease_id pattern: GENE_gene0_POS_REF>ALT
    """
    sb = get_supabase_client()
    try:
        res = (
            sb.table("splice_altering_snv")
            .select("*")
            .eq("disease_id", disease_id)
            .eq("is_representative", True)
            .limit(1)
            .execute()
        )
        data, _, _ = unwrap_execute_result(res)
        row = first_or_none(data)
        if row:
            # normalize coordinate fields (best-effort)
            note = row.get("note")
            chrom = row.get("chromosome") or row.get("chrom") or row.get("chr")
            pos1 = row.get("pos_hg38_1") or row.get("pos1")
            if (chrom is None or pos1 is None) and isinstance(note, str):
                c2, p2 = _parse_coordinate_from_note(note)
                chrom = chrom or c2
                pos1 = pos1 or p2
            row["_chrom"] = chrom
            row["_pos1"] = int(pos1) if pos1 is not None else None
            return row
    except Exception:
        # table/column might not exist yet; continue to fallback
        pass

    # fallback parse
    try:
        gene, gene0, pos, change = disease_id.split("_", 3)
        if gene0 != "gene0":
            return None
        pos_gene0 = int(pos)
        ref, alt = change.split(">", 1)
        return {
            "snv_id": None,
            "disease_id": disease_id,
            "gene_id": gene,
            "pos_gene0": pos_gene0,
            "ref": ref,
            "alt": alt,
            "note": None,
            "is_representative": True,
            "_chrom": None,
            "_pos1": None,
        }
    except Exception:
        return None
