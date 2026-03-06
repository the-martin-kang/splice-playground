from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import requests


@dataclass
class BackendClient:
    """Tiny HTTP client for the FastAPI backend.

    This client is intentionally lightweight and dependency-free (requests only),
    so you can reuse it in validation scripts.
    """

    base_url: str
    timeout_s: int = 30

    def _url(self, path: str) -> str:
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

    def list_diseases(self) -> List[Dict[str, Any]]:
        r = requests.get(self._url("/api/diseases"), timeout=self.timeout_s)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "items" in data:
            return list(data["items"])
        if isinstance(data, list):
            return data
        raise ValueError(f"Unexpected diseases response: {type(data)}")

    def get_window_4000(
        self,
        disease_id: str,
        *,
        window_size: int = 4000,
        strict_ref_check: bool = False,
    ) -> Dict[str, Any]:
        """Fetch a window payload from backend.

        Canonical endpoint:
          GET /api/diseases/{disease_id}/window?window_size={window_size}
        """
        r = requests.get(
            self._url(f"/api/diseases/{disease_id}/window"),
            params={
                "window_size": window_size,
                "strict_ref_check": str(strict_ref_check).lower(),
            },
            timeout=self.timeout_s,
        )
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(
                f"Backend window request failed: status={r.status_code} url={r.url} body={r.text[:800]}"
            ) from e
        return r.json()

    def get_step2_payload(self, disease_id: str, *, include_sequence: bool = False) -> Dict[str, Any]:
        """Fetch STEP2 payload.

        GET /api/diseases/{disease_id}?include_sequence=false
        """
        r = requests.get(
            self._url(f"/api/diseases/{disease_id}"),
            params={"include_sequence": str(include_sequence).lower()},
            timeout=self.timeout_s,
        )
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(
                f"Backend step2 payload request failed: status={r.status_code} url={r.url} body={r.text[:800]}"
            ) from e
        return r.json()

    def get_region(
        self,
        disease_id: str,
        region_type: str,
        region_number: int,
        *,
        include_sequence: bool = True,
    ) -> Dict[str, Any]:
        """Fetch a single region by (type, number).

        GET /api/diseases/{disease_id}/regions/{region_type}/{region_number}
        """
        r = requests.get(
            self._url(f"/api/diseases/{disease_id}/regions/{region_type}/{int(region_number)}"),
            params={"include_sequence": str(include_sequence).lower()},
            timeout=self.timeout_s,
        )
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(
                f"Backend region request failed: status={r.status_code} url={r.url} body={r.text[:800]}"
            ) from e
        return r.json()
