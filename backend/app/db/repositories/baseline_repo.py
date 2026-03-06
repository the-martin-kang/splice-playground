from __future__ import annotations

from typing import Any, Dict, Optional

from app.db.supabase_client import get_supabase_client
from app.db.repositories._helpers import first_or_none, unwrap_execute_result


def get_baseline_result(
    gene_id: str,
    *,
    step: str = "step3",
    model_version: str = "canonical_v1",
) -> Optional[Dict[str, Any]]:
    """Fetch baseline_result row (optional; STEP3/4 will evolve)."""
    sb = get_supabase_client()
    try:
        res = (
            sb.table("baseline_result")
            .select("*")
            .eq("gene_id", gene_id)
            .eq("step", step)
            .eq("model_version", model_version)
            .limit(1)
            .execute()
        )
        data, _, _ = unwrap_execute_result(res)
        return first_or_none(data)
    except Exception:
        return None
