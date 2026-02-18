from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass
class BackendClient:
    base_url: str
    timeout_s: int = 30

    def _url(self, path: str) -> str:
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

    def list_diseases(self) -> List[Dict[str, Any]]:
        r = requests.get(self._url("/api/diseases"), timeout=self.timeout_s)
        r.raise_for_status()
        data = r.json()
        # depending on your API, it might be {"items":[...]} or a list
        if isinstance(data, dict) and "items" in data:
            return list(data["items"])
        if isinstance(data, list):
            return data
        raise ValueError(f"Unexpected diseases response: {type(data)}")

    def get_window_4000(self, disease_id: str) -> Dict[str, Any]:
        """Expect a response that contains at least ref_seq_4000 and alt_seq_4000."""
        r = requests.get(self._url(f"/api/diseases/{disease_id}/window_4000"), timeout=self.timeout_s)
        r.raise_for_status()
        return r.json()
