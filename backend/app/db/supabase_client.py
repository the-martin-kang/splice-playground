from __future__ import annotations

import logging
from functools import lru_cache

from supabase import Client, create_client  # type: ignore

from app.core.config import get_settings

logger = logging.getLogger("app")


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    settings = get_settings()
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
    if not url or not key:
        raise RuntimeError(
            "Supabase env vars missing. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (recommended) or SUPABASE_ANON_KEY."
        )
    return create_client(url, key)


# Backward-compatible alias (some modules used get_supabase())
def get_supabase() -> Client:
    return get_supabase_client()
