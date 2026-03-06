from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.supabase_client import get_supabase_client
from app.db.repositories._helpers import as_list, first_or_none, unwrap_execute_result


REGION_SELECT_BASE = "region_id,gene_id,region_type,region_number,gene_start_idx,gene_end_idx,length"


def list_regions_by_gene(gene_id: str, *, include_sequence: bool = True) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    sel = REGION_SELECT_BASE + (",sequence" if include_sequence else "")
    res = (
        sb.table("region")
        .select(sel)
        .eq("gene_id", gene_id)
        .order("gene_start_idx")
        .execute()
    )
    data, _, _ = unwrap_execute_result(res)
    return as_list(data)


def get_region_by_type_number(
    gene_id: str,
    region_type: str,
    region_number: int,
    *,
    include_sequence: bool = True,
) -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    sel = REGION_SELECT_BASE + (",sequence" if include_sequence else "")
    res = (
        sb.table("region")
        .select(sel)
        .eq("gene_id", gene_id)
        .eq("region_type", region_type)
        .eq("region_number", int(region_number))
        .limit(1)
        .execute()
    )
    data, _, _ = unwrap_execute_result(res)
    return first_or_none(data)
