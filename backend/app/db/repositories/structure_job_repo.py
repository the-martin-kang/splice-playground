from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.repositories._helpers import as_list, first_or_none, unwrap_execute_result
from app.db.supabase_client import get_supabase_client


STRUCTURE_JOB_SELECT = (
    "job_id,state_id,provider,status,created_at,updated_at,external_job_id,"
    "result_payload,error_message"
)


def list_jobs_for_state(state_id: str) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    res = (
        sb.table("structure_job")
        .select(STRUCTURE_JOB_SELECT)
        .eq("state_id", state_id)
        .order("updated_at", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    data, _, _ = unwrap_execute_result(res)
    return as_list(data)



def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("structure_job").select(STRUCTURE_JOB_SELECT).eq("job_id", job_id).limit(1).execute()
    data, _, _ = unwrap_execute_result(res)
    return first_or_none(data)



def list_jobs(*, status: Optional[str] = None, provider: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    q = sb.table("structure_job").select(STRUCTURE_JOB_SELECT).order("created_at").limit(int(limit))
    if status is not None:
        q = q.eq("status", status)
    if provider is not None:
        q = q.eq("provider", provider)
    res = q.execute()
    data, _, _ = unwrap_execute_result(res)
    return as_list(data)



def create_job(
    *,
    state_id: str,
    provider: str,
    status: str = "queued",
    result_payload: Optional[Dict[str, Any]] = None,
    external_job_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    sb = get_supabase_client()
    payload: Dict[str, Any] = {
        "state_id": state_id,
        "provider": provider,
        "status": status,
        "result_payload": result_payload or {},
    }
    if external_job_id is not None:
        payload["external_job_id"] = external_job_id
    if error_message is not None:
        payload["error_message"] = error_message
    res = sb.table("structure_job").insert(payload).execute()
    data, _, _ = unwrap_execute_result(res)
    row = first_or_none(data)
    if not row:
        raise RuntimeError("Failed to create structure_job")
    return row



def update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    result_payload: Optional[Dict[str, Any]] = None,
    external_job_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    sb = get_supabase_client()
    patch: Dict[str, Any] = {}
    if status is not None:
        patch["status"] = status
    if result_payload is not None:
        patch["result_payload"] = result_payload
    if external_job_id is not None:
        patch["external_job_id"] = external_job_id
    if error_message is not None:
        patch["error_message"] = error_message
    if not patch:
        row = get_job(job_id)
        if not row:
            raise RuntimeError(f"structure_job not found: {job_id}")
        return row
    res = sb.table("structure_job").update(patch).eq("job_id", job_id).execute()
    data, _, _ = unwrap_execute_result(res)
    row = first_or_none(data)
    if row:
        return row
    row = get_job(job_id)
    if not row:
        raise RuntimeError(f"structure_job not found after update: {job_id}")
    return row
