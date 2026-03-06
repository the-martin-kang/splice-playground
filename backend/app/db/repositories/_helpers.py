from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def unwrap_execute_result(res: Any) -> Tuple[Any, Optional[Any], Optional[Any]]:
    """Return (data, count, error) for supabase-py execute() results.

    supabase-py v2 returns an object with .data, .count, .error
    In some contexts you may see a dict-like response.
    """
    if hasattr(res, "data"):
        data = res.data
        count = getattr(res, "count", None)
        error = getattr(res, "error", None)
        return data, count, error
    if isinstance(res, dict):
        return res.get("data"), res.get("count"), res.get("error")
    return None, None, None


def first_or_none(data: Any) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def as_list(data: Any) -> List[Dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        return [data]
    return []
