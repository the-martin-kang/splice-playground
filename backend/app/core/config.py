from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional

# Load .env early (best-effort)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    # If python-dotenv isn't installed, env vars must be provided by the runtime.
    pass


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(key)
    if v is None:
        return default
    v = str(v).strip()
    return v if v != "" else default


def _parse_csv(s: Optional[str]) -> List[str]:
    if not s:
        return []
    out: List[str] = []
    for part in s.split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out


@dataclass(frozen=True)
class Settings:
    # App
    APP_NAME: str = _env("APP_NAME", "splice-playground") or "splice-playground"
    APP_VERSION: str = _env("APP_VERSION", "0.1.0") or "0.1.0"
    API_PREFIX: str = _env("API_PREFIX", "/api") or "/api"

    # CORS
    CORS_ORIGINS: List[str] = None  # type: ignore

    # Supabase
    SUPABASE_URL: str = _env("SUPABASE_URL", "") or ""
    SUPABASE_SERVICE_ROLE_KEY: str = (
        _env("SUPABASE_SERVICE_ROLE_KEY") or _env("SUPABASE_SERVICE_KEY") or ""
    )
    SUPABASE_ANON_KEY: str = _env("SUPABASE_ANON_KEY", "") or ""

    # Storage
    STEP1_IMAGE_BUCKET: str = _env("STEP1_IMAGE_BUCKET", "STEP1_image") or "STEP1_image"
    STEP4_STRUCTURE_BUCKET: str = _env("STEP4_STRUCTURE_BUCKET", "structure-assets") or "structure-assets"
    SIGNED_URL_EXPIRES_IN: int = int(_env("SIGNED_URL_EXPIRES_IN", "3600") or "3600")

    # SpliceAI model
    SPLICEAI_MODEL_PATH: str = (
        _env("SPLICEAI_MODEL_PATH", "app/ai_models/spliceai_window=10000.pt")
        or "app/ai_models/spliceai_window=10000.pt"
    )
    SPLICEAI_MODEL_VERSION: str = (
        _env("SPLICEAI_MODEL_VERSION", "spliceai10k_custom_v1") or "spliceai10k_custom_v1"
    )
    SPLICEAI_DEVICE: Optional[str] = _env("SPLICEAI_DEVICE")  # 'cpu'/'cuda'/'mps'

    # External biology APIs (STEP4 baseline ingestion / validation)
    ENSEMBL_REST_BASE: str = _env("ENSEMBL_REST_BASE", "https://rest.ensembl.org") or "https://rest.ensembl.org"
    UNIPROT_REST_BASE: str = _env("UNIPROT_REST_BASE", "https://rest.uniprot.org") or "https://rest.uniprot.org"
    PDBe_API_BASE: str = _env("PDBE_API_BASE", "https://www.ebi.ac.uk/pdbe/api/v2") or "https://www.ebi.ac.uk/pdbe/api/v2"
    ALPHAFOLD_API_BASE: str = (
        _env("ALPHAFOLD_API_BASE", "https://alphafold.ebi.ac.uk/api/prediction")
        or "https://alphafold.ebi.ac.uk/api/prediction"
    )
    RCSB_DOWNLOAD_BASE: str = _env("RCSB_DOWNLOAD_BASE", "https://files.rcsb.org/download") or "https://files.rcsb.org/download"
    HTTP_USER_AGENT: str = _env("HTTP_USER_AGENT", "splice-playground/0.1 (+step4-baseline)") or "splice-playground/0.1 (+step4-baseline)"
    EXTERNAL_API_TIMEOUT_SECONDS: float = float(_env("EXTERNAL_API_TIMEOUT_SECONDS", "30") or "30")

    # NCBI E-utilities courtesy parameters (recommended by NCBI)
    NCBI_TOOL: Optional[str] = _env("NCBI_TOOL", "splice-playground")
    NCBI_EMAIL: Optional[str] = _env("NCBI_EMAIL")
    NCBI_API_KEY: Optional[str] = _env("NCBI_API_KEY")

    def __post_init__(self) -> None:
        origins = _parse_csv(_env("CORS_ORIGINS", ""))
        object.__setattr__(self, "CORS_ORIGINS", origins)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
