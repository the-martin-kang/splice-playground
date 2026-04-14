from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.db.repositories._helpers import as_list, first_or_none, run_with_retry, unwrap_execute_result
from app.db.supabase_client import get_supabase_client


STRUCTURE_JOB_SELECT_SUMMARY = (
    "job_id,state_id,provider,status,created_at,updated_at,external_job_id,error_message"
)

STRUCTURE_JOB_SELECT_DETAIL = (
    "job_id,state_id,provider,status,created_at,updated_at,external_job_id,"
    "result_payload,error_message"
)


def _select_clause(include_payload: bool) -> str:
    return STRUCTURE_JOB_SELECT_DETAIL if include_payload else STRUCTURE_JOB_SELECT_SUMMARY


def list_jobs_for_state(state_id: str, *, include_payload: bool = False, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    q = (
        sb.table("structure_job")
        .select(_select_clause(include_payload))
        .eq("state_id", state_id)
        .order("updated_at", desc=True)
        .order("created_at", desc=True)
    )
    if limit is not None:
        q = q.limit(int(limit))
    res = run_with_retry(lambda: q.execute())
    data, _, _ = unwrap_execute_result(res)
    return as_list(data)


def get_job(job_id: str, *, include_payload: bool = True) -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    q = sb.table("structure_job").select(_select_clause(include_payload)).eq("job_id", job_id).limit(1)
    res = run_with_retry(lambda: q.execute())
    data, _, _ = unwrap_execute_result(res)
    return first_or_none(data)


def list_jobs(*, status: Optional[str] = None, provider: Optional[str] = None, limit: int = 20, include_payload: bool = False) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    q = sb.table("structure_job").select(_select_clause(include_payload)).order("created_at").limit(int(limit))
    if status is not None:
        q = q.eq("status", status)
    if provider is not None:
        q = q.eq("provider", provider)
    res = run_with_retry(lambda: q.execute())
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
    job_id = str(uuid4())
    payload: Dict[str, Any] = {
        "job_id": job_id,
        "state_id": state_id,
        "provider": provider,
        "status": status,
        "result_payload": result_payload or {},
    }
    if external_job_id is not None:
        payload["external_job_id"] = external_job_id
    if error_message is not None:
        payload["error_message"] = error_message
    try:
        res = sb.table("structure_job").insert(payload).execute()
    except Exception:  # noqa: BLE001
        existing = get_job(job_id, include_payload=True)
        if existing:
            return existing
        raise
    data, _, _ = unwrap_execute_result(res)
    row = first_or_none(data)
    if not row:
        row = get_job(job_id, include_payload=True)
    if not row:
        raise RuntimeError("Failed to create structure_job")
    return row


def claim_job_if_queued(
    job_id: str,
    *,
    worker_token: str,
    provider: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Atomically claim a queued job for one worker."""
    sb = get_supabase_client()
    q = sb.table("structure_job").update(
        {
            "status": "running",
            "external_job_id": worker_token,
            "error_message": None,
        }
    ).eq("job_id", job_id).eq("status", "queued")
    if provider is not None:
        q = q.eq("provider", provider)
    res = run_with_retry(lambda: q.execute())
    data, _, _ = unwrap_execute_result(res)
    row = first_or_none(data)
    if row:
        detailed = get_job(job_id, include_payload=True)
        return detailed or row

    current = get_job(job_id, include_payload=True)
    if not current:
        return None
    if str(current.get("status") or "") != "running":
        return None
    if str(current.get("external_job_id") or "") != worker_token:
        return None
    if provider is not None and str(current.get("provider") or "") != provider:
        return None
    return current


def update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    result_payload: Optional[Dict[str, Any]] = None,
    external_job_id: Optional[str] = None,
    error_message: Optional[str] = None,
    include_payload: bool = True,
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
        row = get_job(job_id, include_payload=include_payload)
        if not row:
            raise RuntimeError(f"structure_job not found: {job_id}")
        return row
    q = sb.table("structure_job").update(patch).eq("job_id", job_id)
    run_with_retry(lambda: q.execute())
    row = get_job(job_id, include_payload=include_payload)
    if not row:
        raise RuntimeError(f"structure_job not found after update: {job_id}")
    return row
