from __future__ import annotations

import io
from typing import Optional, Tuple

from app.core.config import get_settings
from app.db.supabase_client import get_supabase_client


def _split_bucket_and_path(stored_path: str, default_bucket: str) -> Tuple[str, str]:
    """Handle stored object paths in two styles.

    1) "bucket/path/to/file.ext"  -> bucket=bucket, path=path/to/file.ext
    2) "path/to/file.ext"         -> bucket=default_bucket, path=path/to/file.ext
    """
    p = (stored_path or "").lstrip("/")
    if not p:
        return default_bucket, ""

    if "/" in p:
        first, rest = p.split("/", 1)
        if first == default_bucket:
            return first, rest
    return default_bucket, p


def create_signed_storage_url(bucket: str, object_path: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Create a signed URL for an arbitrary Supabase Storage object."""
    if not object_path:
        return None, None

    sb = get_supabase_client()
    expires = int(get_settings().SIGNED_URL_EXPIRES_IN)
    res = sb.storage.from_(bucket).create_signed_url(object_path, expires)
    if isinstance(res, dict):
        url = res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
    else:
        url = getattr(res, "signedURL", None) or getattr(res, "signedUrl", None)
    return url, expires


def create_signed_url(image_path: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Backward-compatible helper used by STEP1 images."""
    if not image_path:
        return None, None

    settings = get_settings()
    bucket, obj_path = _split_bucket_and_path(image_path, settings.STEP1_IMAGE_BUCKET)
    if not obj_path:
        return None, None
    return create_signed_storage_url(bucket, obj_path)


def upload_bytes_to_storage(
    *,
    bucket: str,
    object_path: str,
    data: bytes,
    content_type: Optional[str] = None,
    upsert: bool = True,
) -> None:
    """Upload a small/medium binary blob to Supabase Storage.

    Notes:
    - Supabase Python clients vary slightly in accepted payload types; BytesIO is the
      most broadly compatible.
    - This helper is primarily used by STEP4 baseline ingestion scripts, not hot path APIs.
    """
    if not bucket:
        raise ValueError("bucket is required")
    if not object_path:
        raise ValueError("object_path is required")

    sb = get_supabase_client()
    file_options = {"upsert": "true" if upsert else "false"}
    if content_type:
        file_options["content-type"] = content_type

    payload = io.BytesIO(data)
    try:
        sb.storage.from_(bucket).upload(object_path, payload, file_options=file_options)
    except Exception:
        # Some versions prefer raw bytes over BytesIO.
        sb.storage.from_(bucket).upload(object_path, data, file_options=file_options)



def download_storage_bytes(bucket: str, object_path: str) -> bytes:
    """Download a storage object by creating a short-lived signed URL and fetching it."""
    import requests

    url, _ = create_signed_storage_url(bucket, object_path)
    if not url:
        raise ValueError("Could not create signed URL for storage download")
    res = requests.get(url, timeout=60)
    res.raise_for_status()
    return res.content
