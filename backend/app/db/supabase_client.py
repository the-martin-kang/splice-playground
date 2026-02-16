# app/db/supabase_client.py
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypeVar

from app.core.config import get_settings

# supabase-py
from supabase import Client, create_client

# postgrest 에러(있으면 더 자세히 잡음)
try:
    from postgrest.exceptions import APIError as PostgrestAPIError  # type: ignore
except Exception:  # pragma: no cover
    PostgrestAPIError = Exception  # type: ignore


# -----------------------
# Exceptions
# -----------------------
class DBError(Exception):
    """DB layer base exception."""


class DBQueryError(DBError):
    """Supabase/PostgREST query failed."""


class DBNotFoundError(DBError):
    """Requested resource not found."""


class DBConflictError(DBError):
    """Unique constraint / conflict error."""


T = TypeVar("T")


@dataclass(frozen=True)
class DBResult:
    data: Any
    count: Optional[int] = None


# -----------------------
# Client (singleton)
# -----------------------
@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Create Supabase client using service role key.
    - Cached for process lifetime
    - Safe for typical FastAPI usage (sync)
    """
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)


# -----------------------
# Helpers
# -----------------------
def _get_data(resp: Any) -> Any:
    # supabase-py v2 response typically has .data
    if hasattr(resp, "data"):
        return resp.data
    # fallback
    return getattr(resp, "get", lambda *_: None)("data")


def _get_count(resp: Any) -> Optional[int]:
    return getattr(resp, "count", None)


def execute(query: Any) -> DBResult:
    """
    Execute a built postgrest query safely and normalize response.
    """
    try:
        resp = query.execute()
        return DBResult(data=_get_data(resp), count=_get_count(resp))
    except PostgrestAPIError as e:
        # Often contains message/details
        raise DBQueryError(str(e)) from e
    except Exception as e:
        raise DBQueryError(str(e)) from e


def ensure_list(data: Any) -> List[Dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    # sometimes .single() yields dict
    if isinstance(data, dict):
        return [data]
    raise DBQueryError(f"Unexpected response data type: {type(data)}")


def ensure_one(rows: Sequence[T], *, not_found_message: str) -> T:
    if not rows:
        raise DBNotFoundError(not_found_message)
    if len(rows) > 1:
        # Not fatal, but indicates DB expectation violation
        raise DBQueryError(f"Expected 1 row, got {len(rows)}. {not_found_message}")
    return rows[0]
