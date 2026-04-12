from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.supabase_client import get_supabase_client
from app.db.repositories._helpers import as_list, first_or_none, unwrap_execute_result


_REGION_SELECT_WITH_CDS = (
    "region_id,gene_id,region_type,region_number,gene_start_idx,gene_end_idx,length,"
    "cds_start_offset,cds_end_offset"
)
_REGION_SELECT_FALLBACK = "region_id,gene_id,region_type,region_number,gene_start_idx,gene_end_idx,length"


def _select_region_rows(*, gene_id: str, include_sequence: bool, region_type: Optional[str] = None, region_number: Optional[int] = None) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    select = _REGION_SELECT_WITH_CDS + (",sequence" if include_sequence else "")

    def _query(sel: str):
        q = sb.table("region").select(sel).eq("gene_id", gene_id)
        if region_type is not None:
            q = q.eq("region_type", region_type)
        if region_number is not None:
            q = q.eq("region_number", int(region_number)).limit(1)
        return q.order("gene_start_idx").execute()

    try:
        res = _query(select)
    except Exception:
        fallback = _REGION_SELECT_FALLBACK + (",sequence" if include_sequence else "")
        res = _query(fallback)

    data, _, _ = unwrap_execute_result(res)
    rows = as_list(data)
    for row in rows:
        row.setdefault("cds_start_offset", None)
        row.setdefault("cds_end_offset", None)
    return rows



def list_regions_by_gene(gene_id: str, *, include_sequence: bool = True) -> List[Dict[str, Any]]:
    return _select_region_rows(gene_id=gene_id, include_sequence=include_sequence)



def get_region_by_type_number(
    gene_id: str,
    region_type: str,
    region_number: int,
    *,
    include_sequence: bool = True,
) -> Optional[Dict[str, Any]]:
    rows = _select_region_rows(
        gene_id=gene_id,
        include_sequence=include_sequence,
        region_type=region_type,
        region_number=region_number,
    )
    return first_or_none(rows)
