from __future__ import annotations

from typing import Any, Dict, Optional

from app.db.supabase_client import get_supabase_client
from app.db.repositories._helpers import first_or_none, unwrap_execute_result


def get_target_window(disease_id: str) -> Optional[Dict[str, Any]]:
    """Return the editing_target_window row for a disease (if exists)."""
    sb = get_supabase_client()
    try:
        res = (
            sb.table("editing_target_window")
            .select("*")
            .eq("disease_id", disease_id)
            .order("created_at", desc=False)
            .limit(1)
            .execute()
        )
        data, _, _ = unwrap_execute_result(res)
        return first_or_none(data)
    except Exception:
        # table might not exist in early dev
        return None
