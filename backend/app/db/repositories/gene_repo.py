from __future__ import annotations

from typing import Any, Dict, Optional

from app.db.supabase_client import get_supabase_client
from app.db.repositories._helpers import first_or_none, unwrap_execute_result


def get_gene(gene_id: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("gene").select("*").eq("gene_id", gene_id).limit(1).execute()
    data, _, _ = unwrap_execute_result(res)
    return first_or_none(data)
