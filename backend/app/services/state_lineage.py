from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.db.repositories import state_repo


def parse_stored_edits(applied_edit_obj: Any) -> List[Dict[str, Any]]:
    """Normalize stored ``applied_edit`` into a list of {pos, from, to} dicts."""
    if not applied_edit_obj:
        return []
    obj = applied_edit_obj
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            return []

    edits = obj.get("edits") if isinstance(obj, dict) else None
    if not isinstance(edits, list):
        return []

    out: List[Dict[str, Any]] = []
    for it in edits:
        try:
            out.append(
                {
                    "pos": int(it.get("pos")),
                    "from": str(it.get("from") or "N").upper(),
                    "to": str(it.get("to") or "N").upper(),
                }
            )
        except Exception:
            continue
    return out


def load_parent_chain_rows(parent_state_id: Optional[str], *, disease_id: str) -> List[Dict[str, Any]]:
    """Return parent states from root -> immediate parent.

    The chain is validated for cycles and disease consistency.
    """
    seen = set()
    rows: List[Dict[str, Any]] = []
    cur = parent_state_id
    while cur:
        if cur in seen:
            raise HTTPException(status_code=400, detail="parent_state_id cycle detected")
        seen.add(cur)

        row = state_repo.get_state(cur)
        if not row:
            raise HTTPException(status_code=404, detail=f"parent_state_id not found: {cur}")
        if str(row.get("disease_id")) != disease_id:
            raise HTTPException(status_code=400, detail="parent_state_id belongs to a different disease")

        rows.append(row)
        cur = row.get("parent_state_id")
    rows.reverse()
    return rows


def load_parent_chain_edits(parent_state_id: Optional[str], *, disease_id: str) -> List[Dict[str, Any]]:
    edits: List[Dict[str, Any]] = []
    for row in load_parent_chain_rows(parent_state_id, disease_id=disease_id):
        edits.extend(parse_stored_edits(row.get("applied_edit")))
    return edits


def collect_effective_state_edits(
    state_row: Dict[str, Any],
    *,
    include_parent_chain: bool = True,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return (effective_edits, lineage_ids) for a state.

    ``effective_edits`` are ordered exactly as they should be applied to the
    displayed disease sequence: parent chain first, then the current state's
    own edits.

    ``lineage_ids`` is ordered root -> current.
    """
    disease_id = str(state_row.get("disease_id") or "")
    if not disease_id:
        raise HTTPException(status_code=500, detail="user_state.disease_id is missing")

    edits: List[Dict[str, Any]] = []
    lineage_ids: List[str] = []

    parent_state_id = state_row.get("parent_state_id") if include_parent_chain else None
    parent_rows = load_parent_chain_rows(parent_state_id, disease_id=disease_id)
    for row in parent_rows:
        lineage_ids.append(str(row.get("state_id")))
        edits.extend(parse_stored_edits(row.get("applied_edit")))

    current_state_id = state_row.get("state_id")
    if current_state_id:
        lineage_ids.append(str(current_state_id))
    edits.extend(parse_stored_edits(state_row.get("applied_edit")))
    return edits, lineage_ids
