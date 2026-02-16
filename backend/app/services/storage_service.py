# app/services/storage_service.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests

from app.core.config import get_settings
from app.db.supabase_client import DBQueryError, get_supabase_client


@dataclass(frozen=True)
class SignedUrl:
    url: str
    expires_in: int


class StorageService:
    """
    B 방식: private bucket + signed url
    DB에는 image_path = "BUCKET_NAME/path/to/file.png" 형태로 저장.
    API 응답에는 signed url(full url)을 내려준다.
    """

    # 간단 캐시(프로세스 단위). 이미지 6개 정도면 충분.
    _cache: Dict[Tuple[str, str, int], Tuple[str, float]] = {}  # (bucket,key,ttl) -> (url, expire_at_epoch)

    @staticmethod
    def split_bucket_key(path: str) -> Tuple[str, str]:
        """
        "STEP1_image/CFTR.png" -> ("STEP1_image", "CFTR.png")
        """
        if not path:
            raise ValueError("image_path is empty")
        p = str(path).lstrip("/")
        if "/" not in p:
            raise ValueError(f"image_path must be 'bucket/key'. got: {path!r}")
        bucket, key = p.split("/", 1)
        bucket = bucket.strip()
        key = key.strip()
        if not bucket or not key:
            raise ValueError(f"invalid image_path: {path!r}")
        return bucket, key

    @staticmethod
    def _normalize_signed_url(signed_url: str) -> str:
        """
        Supabase signedURL가 상대경로로 올 수 있어서 full url로 만든다.
        - if startswith http -> 그대로
        - if startswith "/object/sign/..." -> {SUPABASE_URL}/storage/v1 + signedURL
        - else -> best effort join
        """
        s = get_settings()
        base = s.supabase_url.rstrip("/")
        storage_base = f"{base}/storage/v1"

        u = (signed_url or "").strip()
        if not u:
            raise DBQueryError("signed url is empty")

        if u.startswith("http://") or u.startswith("https://"):
            return u

        if u.startswith("/"):
            # usually "/object/sign/..."
            return f"{storage_base}{u}"

        # e.g. "object/sign/..." or "storage/v1/object/sign/..."
        if u.startswith("storage/v1/"):
            return f"{base}/{u}"
        if u.startswith("object/"):
            return f"{storage_base}/{u}"

        # fallback
        return f"{storage_base}/{u.lstrip('/')}"

    @classmethod
    def create_signed_url_for_image_path(
        cls,
        image_path: str,
        *,
        expires_in: Optional[int] = None,
    ) -> SignedUrl:
        """
        image_path: "STEP1_image/CFTR.png"
        returns: SignedUrl(url=..., expires_in=...)
        """
        settings = get_settings()
        ttl = int(expires_in if expires_in is not None else settings.signed_url_ttl_seconds)
        bucket, key = cls.split_bucket_key(image_path)

        cache_key = (bucket, key, ttl)
        now = time.time()
        cached = cls._cache.get(cache_key)
        if cached:
            url, exp_at = cached
            # 만료 60초 전까진 캐시 사용
            if exp_at - 60 > now:
                return SignedUrl(url=url, expires_in=ttl)

        # 1) supabase-py 우선 시도
        try:
            sb = get_supabase_client()
            # 공식 문서: supabase.storage.from_("bucket").create_signed_url("path", expires_in)
            resp = sb.storage.from_(bucket).create_signed_url(key, ttl)
            signed = cls._extract_signed_url(resp)
            full = cls._normalize_signed_url(signed)
            cls._cache[cache_key] = (full, now + ttl)
            return SignedUrl(url=full, expires_in=ttl)
        except Exception:
            # 2) REST fallback
            full = cls._create_signed_url_via_rest(bucket=bucket, key=key, ttl=ttl)
            cls._cache[cache_key] = (full, now + ttl)
            return SignedUrl(url=full, expires_in=ttl)

    @staticmethod
    def _extract_signed_url(resp: Any) -> str:
        """
        supabase-py / storage response에서 signedURL 계열 필드를 최대한 유연하게 뽑는다.
        """
        # dict
        if isinstance(resp, dict):
            # 형태가 다양한 경우들 방어
            for k in ("signedURL", "signedUrl", "signed_url", "url"):
                if k in resp and resp[k]:
                    return str(resp[k])
            # data 내부
            data = resp.get("data")
            if isinstance(data, dict):
                for k in ("signedURL", "signedUrl", "signed_url", "url"):
                    if k in data and data[k]:
                        return str(data[k])

        # 객체 with data
        if hasattr(resp, "data"):
            data = resp.data
            if isinstance(data, dict):
                for k in ("signedURL", "signedUrl", "signed_url", "url"):
                    if k in data and data[k]:
                        return str(data[k])

        # 객체 자체가 signedURL 문자열일 가능성
        if isinstance(resp, str):
            return resp

        raise DBQueryError(f"Could not extract signed url from response: {type(resp)}")

    @staticmethod
    def _create_signed_url_via_rest(*, bucket: str, key: str, ttl: int) -> str:
        """
        REST API fallback:
          POST {SUPABASE_URL}/storage/v1/object/sign/{bucket}/{key}
          body: {"expiresIn": ttl}
          headers: Authorization Bearer service_key + apikey
        """
        s = get_settings()
        base = s.supabase_url.rstrip("/")
        url = f"{base}/storage/v1/object/sign/{bucket}/{key}"

        headers = {
            "Authorization": f"Bearer {s.supabase_service_key}",
            "apikey": s.supabase_service_key,
            "Content-Type": "application/json",
        }
        body = {"expiresIn": int(ttl)}

        r = requests.post(url, headers=headers, json=body, timeout=20)
        if r.status_code >= 400:
            raise DBQueryError(f"Signed URL REST failed ({r.status_code}): {r.text}")

        j = r.json()
        signed = j.get("signedURL") or j.get("signedUrl") or j.get("signed_url") or j.get("url")
        if not signed:
            raise DBQueryError(f"Signed URL REST response missing signedURL: {j}")

        # 보통 signedURL은 "/object/sign/..." 형태라 normalize 필요
        return StorageService._normalize_signed_url(str(signed))
