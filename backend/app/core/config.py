# app/core/config.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Tuple

from dotenv import load_dotenv

# .env 로딩 (이미 OS env에 있는 값은 덮어쓰지 않음)
# - 로컬: backend/에서 실행하면 자동으로 .env를 찾음
# - 배포: App Runner 환경변수 사용
load_dotenv(override=False)


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    return v if v != "" else default


def _env_required(name: str) -> str:
    v = _env(name)
    if v is None:
        raise RuntimeError(
            f"Missing required environment variable: {name}\n"
            f"Add it to .env (local) or App Runner env (prod)."
        )
    return v


def _env_bool(name: str, default: bool = False) -> bool:
    v = _env(name)
    if v is None:
        return default
    s = v.strip().lower()
    if s in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    v = _env(name)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _parse_str_list(value: Optional[str]) -> Tuple[str, ...]:
    """
    Accept:
      - comma-separated: "http://localhost:3000,https://foo.vercel.app"
      - json list: '["http://localhost:3000","https://foo.vercel.app"]'
    """
    if not value:
        return tuple()

    s = value.strip()
    if s.startswith("["):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                items = [str(x).strip() for x in arr if str(x).strip()]
                return tuple(items)
        except json.JSONDecodeError:
            pass

    items = [x.strip() for x in s.split(",") if x.strip()]
    return tuple(items)


@dataclass(frozen=True)
class Settings:
    # app
    app_name: str
    env: str
    debug: bool
    log_level: str
    api_prefix: str

    # cors
    cors_origins: Tuple[str, ...]
    cors_allow_origin_regex: Optional[str]
    cors_allow_credentials: bool

    # storage (B 방식: signed url)
    signed_url_ttl_seconds: int

    # supabase
    supabase_url: str
    supabase_service_key: str

    # optional startup checks
    check_supabase_on_startup: bool

    # docs
    disable_docs: bool

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in {"prod", "production"}

    @property
    def docs_url(self) -> Optional[str]:
        # prod에서 docs 꺼버리고 싶으면 DISABLE_DOCS=true
        return None if self.disable_docs else "/docs"

    @property
    def redoc_url(self) -> Optional[str]:
        return None if self.disable_docs else "/redoc"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    app_name = _env("APP_NAME", "splice-playground")
    env = _env("ENV", "local")
    debug = _env_bool("DEBUG", default=(env == "local"))
    log_level = _env("LOG_LEVEL", "INFO")
    api_prefix = _env("API_PREFIX", "/api")

    cors_origins = _parse_str_list(_env("CORS_ORIGINS"))
    cors_allow_origin_regex = _env("CORS_ALLOW_ORIGIN_REGEX")
    cors_allow_credentials = _env_bool("CORS_ALLOW_CREDENTIALS", default=False)

    # 이미지 Signed URL TTL (초)
    signed_url_ttl_seconds = _env_int("SIGNED_URL_TTL_SECONDS", default=60 * 60 * 24)  # 24h

    supabase_url = _env_required("SUPABASE_URL")
    supabase_service_key = _env_required("SUPABASE_SERVICE_KEY")

    check_supabase_on_startup = _env_bool("CHECK_SUPABASE_ON_STARTUP", default=False)
    disable_docs = _env_bool("DISABLE_DOCS", default=False)

    # CORS 안전장치: credentials=true 인데 origins에 "*" 쓰면 브라우저 정책상 안 맞음
    if cors_allow_credentials and ("*" in cors_origins):
        raise RuntimeError("Invalid CORS config: CORS_ALLOW_CREDENTIALS=true with CORS_ORIGINS containing '*'")

    return Settings(
        app_name=app_name,
        env=env,
        debug=debug,
        log_level=log_level,
        api_prefix=api_prefix,
        cors_origins=cors_origins,
        cors_allow_origin_regex=cors_allow_origin_regex,
        cors_allow_credentials=cors_allow_credentials,
        signed_url_ttl_seconds=signed_url_ttl_seconds,
        supabase_url=supabase_url,
        supabase_service_key=supabase_service_key,
        check_supabase_on_startup=check_supabase_on_startup,
        disable_docs=disable_docs,
    )
