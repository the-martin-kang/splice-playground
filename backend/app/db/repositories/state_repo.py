
from __future__ import annotations

from typing import Any, Dict, Optional

from app.db.supabase_client import get_supabase_client
from app.db.repositories._helpers import first_or_none, unwrap_execute_result


def create_state(
    disease_id: str,
    *,
    gene_id: Optional[str] = None,
    applied_edit: Optional[dict] = None,
    parent_state_id: Optional[str] = None,
) -> Dict[str, Any]:
    sb = get_supabase_client()
    payload: Dict[str, Any] = {"disease_id": disease_id}
    if gene_id is not None:
        payload["gene_id"] = gene_id
    if parent_state_id:
        payload["parent_state_id"] = parent_state_id
    if applied_edit is not None:
        payload["applied_edit"] = applied_edit

    try:
        res = sb.table("user_state").insert(payload).execute()
    except Exception as e:
        msg = str(e)
        if gene_id is not None and ("gene_id" in msg and ("column" in msg or "schema cache" in msg or "record" in msg)):
            payload.pop("gene_id", None)
            res = sb.table("user_state").insert(payload).execute()
        else:
            raise

    data, _, _ = unwrap_execute_result(res)
    row = first_or_none(data)
    if not row:
        raise RuntimeError("Failed to create user_state (no row returned)")
    return row


def get_state(state_id: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("user_state").select("*").eq("state_id", state_id).limit(1).execute()
    data, _, _ = unwrap_execute_result(res)
    return first_or_none(data)
