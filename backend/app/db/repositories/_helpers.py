from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from app.core.config import get_settings

T = TypeVar("T")


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


def is_retryable_exception(exc: Exception) -> bool:
    msg = str(exc).lower()
    needles = (
        "timeout",
        "timed out",
        "connection reset",
        "connection aborted",
        "connection closed",
        "connection terminated",
        "temporarily unavailable",
        "server disconnected",
        "502",
        "503",
        "504",
        "522",
        "544",
    )
    return any(n in msg for n in needles)


def run_with_retry(fn: Callable[[], T], *, attempts: Optional[int] = None, backoff_seconds: Optional[float] = None) -> T:
    settings = get_settings()
    max_attempts = int(attempts or settings.SUPABASE_RETRY_ATTEMPTS or 1)
    base_sleep = float(backoff_seconds or settings.SUPABASE_RETRY_BACKOFF_SECONDS or 0.75)
    last_exc: Optional[Exception] = None
    for i in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i >= max_attempts - 1 or not is_retryable_exception(exc):
                raise
            time.sleep(base_sleep * (2**i))
    assert last_exc is not None
    raise last_exc
