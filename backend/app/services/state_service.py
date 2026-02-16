# app/services/state_service.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.repositories.disease_repo import DiseaseRepo
from app.db.repositories.gene_repo import GeneRepo
from app.db.repositories.state_repo import StateRepo
from app.schemas.state import CreateStateResponse

_ALLOWED_BASES = {"A", "C", "G", "T", "N"}


def _validate_applied_edit(applied_edit: Dict[str, Any], gene_length: int) -> Dict[str, Any]:
    """
    applied_edit 형식:
    {
      "type": "user",
      "edits": [
        { "pos": 109442, "from": "G", "to": "A" },
        ...
      ]
    }

    - gene0 pos 범위 체크
    - base 체크
    - 중복 pos 방지
    """
    if not isinstance(applied_edit, dict):
        raise ValueError("applied_edit must be an object")

    t = applied_edit.get("type")
    if not isinstance(t, str) or not t:
        raise ValueError("applied_edit.type must be a non-empty string")

    edits = applied_edit.get("edits")
    if not isinstance(edits, list):
        raise ValueError("applied_edit.edits must be an array")

    seen_pos = set()
    cleaned: List[Dict[str, Any]] = []

    for i, e in enumerate(edits):
        if not isinstance(e, dict):
            raise ValueError(f"applied_edit.edits[{i}] must be an object")

        pos = e.get("pos")
        frm = e.get("from")
        to = e.get("to")

        if not isinstance(pos, int):
            raise ValueError(f"applied_edit.edits[{i}].pos must be int")
        if pos < 0 or pos >= int(gene_length):
            raise ValueError(f"applied_edit.edits[{i}].pos out of range: {pos} (gene_length={gene_length})")

        if not isinstance(frm, str) or len(frm.strip()) != 1:
            raise ValueError(f"applied_edit.edits[{i}].from must be 1 char")
        if not isinstance(to, str) or len(to.strip()) != 1:
            raise ValueError(f"applied_edit.edits[{i}].to must be 1 char")

        frm_u = frm.strip().upper()
        to_u = to.strip().upper()

        if frm_u not in _ALLOWED_BASES or to_u not in _ALLOWED_BASES:
            raise ValueError(f"applied_edit.edits[{i}] bases must be in {_ALLOWED_BASES}")

        if frm_u == to_u:
            raise ValueError(f"applied_edit.edits[{i}] from and to must differ")

        if pos in seen_pos:
            raise ValueError(f"duplicate edit position not allowed: pos={pos}")
        seen_pos.add(pos)

        cleaned.append({"pos": pos, "from": frm_u, "to": to_u})

    cleaned.sort(key=lambda x: x["pos"])
    return {"type": t, "edits": cleaned}


class StateService:
    @staticmethod
    def create_state(
        *,
        disease_id: str,
        applied_edit: Dict[str, Any],
        parent_state_id: Optional[str] = None,
    ) -> CreateStateResponse:
        disease = DiseaseRepo.get_disease_by_id(disease_id, select="disease_id,gene_id")
        gene_id = str(disease["gene_id"])

        gene = GeneRepo.get_gene_by_id(gene_id, select="gene_id,length")
        gene_length = int(gene["length"])

        cleaned_edit = _validate_applied_edit(applied_edit, gene_length)

        if parent_state_id:
            parent = StateRepo.get_state_by_id(parent_state_id, select="state_id,disease_id,gene_id")
            if str(parent["disease_id"]) != disease_id:
                raise ValueError("parent_state_id belongs to different disease")
            if str(parent["gene_id"]) != gene_id:
                raise ValueError("parent_state_id belongs to different gene")

        state_id = StateRepo.create_state(
            disease_id=disease_id,
            gene_id=gene_id,
            applied_edit=cleaned_edit,
            parent_state_id=parent_state_id,
        )

        return CreateStateResponse(state_id=state_id)
