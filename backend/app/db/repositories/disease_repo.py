from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.db.supabase_client import get_supabase_client
from app.db.repositories._helpers import as_list, first_or_none, unwrap_execute_result


def list_diseases(limit: int = 100, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    sb = get_supabase_client()
    q = (
        sb.table("disease")
        .select("disease_id,disease_name,description,gene_id,image_path", count="exact")
        .range(offset, offset + limit - 1)
        .order("disease_id")
    )
    res = q.execute()
    data, count, _ = unwrap_execute_result(res)
    items = as_list(data)
    total = int(count) if count is not None else len(items)
    return items, total


def get_disease(disease_id: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("disease").select("*").eq("disease_id", disease_id).limit(1).execute()
    data, _, _ = unwrap_execute_result(res)
    return first_or_none(data)


def get_gene_ids_for_disease(disease_id: str) -> List[str]:
    """Return gene_id(s) for a disease.

    New schema: disease.gene_id exists.
    Fallback: disease_gene join table.
    """
    d = get_disease(disease_id)
    if d:
        gid = d.get("gene_id")
        if gid:
            return [str(gid)]

    # fallback join table
    sb = get_supabase_client()
    res = (
        sb.table("disease_gene")
        .select("gene_id")
        .eq("disease_id", disease_id)
        .order("gene_id")
        .execute()
    )
    data, _, _ = unwrap_execute_result(res)
    rows = as_list(data)
    return [str(r["gene_id"]) for r in rows if r.get("gene_id")]
