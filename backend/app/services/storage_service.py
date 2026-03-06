from __future__ import annotations

from typing import Optional, Tuple

from app.core.config import get_settings
from app.db.supabase_client import get_supabase_client


def _split_bucket_and_path(image_path: str, default_bucket: str) -> Tuple[str, str]:
    """Handle stored image_path in two styles:

    1) "STEP1_image/CFTR.png"  -> bucket=STEP1_image, path=CFTR.png
    2) "CFTR.png"             -> bucket=STEP1_image (default), path=CFTR.png
    """
    p = (image_path or "").lstrip("/")
    if not p:
        return default_bucket, ""

    if "/" in p:
        first, rest = p.split("/", 1)
        # If the first segment matches the bucket name, treat it as bucket.
        if first == default_bucket:
            return first, rest
    return default_bucket, p


def create_signed_url(image_path: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Create a signed URL for a file in Supabase Storage (B 방식).

    Returns (url, expires_in_seconds).
    """
    if not image_path:
        return None, None

    settings = get_settings()
    bucket, obj_path = _split_bucket_and_path(image_path, settings.STEP1_IMAGE_BUCKET)
    if not obj_path:
        return None, None

    sb = get_supabase_client()
    expires = int(settings.SIGNED_URL_EXPIRES_IN)

    # supabase-py returns dict-like response
    res = sb.storage.from_(bucket).create_signed_url(obj_path, expires)
    if isinstance(res, dict):
        url = res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
    else:
        url = getattr(res, "signedURL", None) or getattr(res, "signedUrl", None)
    return url, expires
