from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import HTTPException

from app.db.repositories import disease_repo, gene_repo, region_repo, state_repo
from app.schemas.state import AppliedEdit, CreateStateRequest, Edit, StatePublic


_ALLOWED = {"A", "C", "G", "T", "N"}


def _normalize_applied_edit(applied: Optional[AppliedEdit]) -> dict:
    if applied is None:
        return {"type": "user", "edits": []}

    edits = []
    for e in applied.edits:
        edits.append({"pos": int(e.pos_gene0), "from": e.from_base.upper(), "to": e.to_base.upper()})
    return {"type": applied.type, "edits": edits}


def _get_representative_snv_from_disease_id_or_db(disease_id: str) -> Optional[dict]:
    # Try DB first via supabase client indirectly not to add more repository files.
    try:
        from app.db.supabase_client import get_supabase_client
        sb = get_supabase_client()
        res = (
            sb.table("splice_altering_snv")
            .select("*")
            .eq("disease_id", disease_id)
            .eq("is_representative", True)
            .limit(1)
            .execute()
        )
        data = res.data if hasattr(res, "data") else res.get("data")
        if data:
            if isinstance(data, list):
                return data[0] if data else None
            return data
    except Exception:
        pass

    # Fallback: parse disease_id like BRCA1_gene0_106454_G>A
    try:
        gene, tag, pos, change = disease_id.split("_", 3)
        if tag != "gene0":
            return None
        ref, alt = change.split(">", 1)
        return {"gene_id": gene, "pos_gene0": int(pos), "ref": ref, "alt": alt, "is_representative": True}
    except Exception:
        return None


def _build_gene_sequence(gene_len: int, regions: List[dict]) -> str:
    arr = ["N"] * int(gene_len)
    for r in regions:
        s = int(r.get("gene_start_idx", 0))
        e = int(r.get("gene_end_idx", 0))
        seq = (r.get("sequence") or "").upper()
        if not seq:
            continue
        # region_end is inclusive in DB
        expected = e - s + 1
        if expected != len(seq):
            m = min(expected, len(seq))
            seq = seq[:m]
            e = s + m - 1
        if s < 0 or e >= gene_len or s > e:
            continue
        arr[s:e+1] = list(seq)
    return "".join(arr)


def _parse_stored_edits(applied_edit_obj) -> List[dict]:
    if not applied_edit_obj:
        return []
    edits = applied_edit_obj.get("edits") if isinstance(applied_edit_obj, dict) else None
    if not isinstance(edits, list):
        return []
    out = []
    for it in edits:
        try:
            pos = int(it.get("pos"))
            fb = str(it.get("from")).upper()
            tb = str(it.get("to")).upper()
            out.append({"pos": pos, "from": fb, "to": tb})
        except Exception:
            continue
    return out


def _load_parent_chain_edits(parent_state_id: Optional[str], disease_id: str) -> List[dict]:
    out: List[dict] = []
    seen = set()
    cur = parent_state_id
    chain = []
    while cur:
        if cur in seen:
            raise HTTPException(status_code=400, detail="parent_state_id cycle detected")
        seen.add(cur)
        row = state_repo.get_state(cur)
        if not row:
            raise HTTPException(status_code=404, detail=f"parent_state_id not found: {cur}")
        if str(row.get("disease_id")) != disease_id:
            raise HTTPException(status_code=400, detail="parent_state_id belongs to a different disease")
        chain.append(row)
        cur = row.get("parent_state_id")
    # oldest parent first
    for row in reversed(chain):
        out.extend(_parse_stored_edits(row.get("applied_edit")))
    return out


def _current_sequence_for_edits(disease_id: str, gene_id: str, gene_len: int, parent_state_id: Optional[str]) -> List[str]:
    regions = region_repo.list_regions_by_gene(gene_id, include_sequence=True)
    seq = list(_build_gene_sequence(gene_len, regions))

    # The UI edits the disease sequence, so representative disease SNV is already present.
    rep = _get_representative_snv_from_disease_id_or_db(disease_id)
    if rep is not None:
        pos = int(rep["pos_gene0"])
        if 0 <= pos < len(seq):
            seq[pos] = str(rep["alt"]).upper()

    # Apply parent state edits on top.
    for e in _load_parent_chain_edits(parent_state_id, disease_id):
        pos = e["pos"]
        if 0 <= pos < len(seq):
            seq[pos] = e["to"]
    return seq


def _validate_request_edits(req: CreateStateRequest, *, disease_id: str, gene_id: str, gene_len: int) -> dict:
    applied = _normalize_applied_edit(req.applied_edit)
    current_seq = _current_sequence_for_edits(disease_id, gene_id, gene_len, req.parent_state_id)

    seen_pos = set()
    cleaned = []
    for raw in applied["edits"]:
        pos = int(raw["pos"])
        fb = str(raw["from"]).upper()
        tb = str(raw["to"]).upper()
        if pos < 0 or pos >= gene_len:
            raise HTTPException(status_code=400, detail=f"Edit pos out of range: {pos} (gene_length={gene_len})")
        if fb not in _ALLOWED or tb not in _ALLOWED:
            raise HTTPException(status_code=400, detail=f"Edit base must be one of {_ALLOWED}: {raw}")
        if fb == tb:
            raise HTTPException(status_code=400, detail=f"Edit from/to must differ: {raw}")
        if pos in seen_pos:
            raise HTTPException(status_code=400, detail=f"Duplicate edit position: {pos}")
        seen_pos.add(pos)
        cur = current_seq[pos].upper()
        if cur != fb:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Edit ref mismatch against current displayed sequence",
                    "pos_gene0": pos,
                    "expected_current_base": cur,
                    "provided_from": fb,
                    "provided_to": tb,
                    "disease_id": disease_id,
                    "hint": "The editor works on the disease sequence (representative SNV already applied), not the raw reference sequence.",
                },
            )
        cleaned.append({"pos": pos, "from": fb, "to": tb})
        current_seq[pos] = tb

    return {"type": applied["type"], "edits": cleaned}


def create_state_for_disease(disease_id: str, req: CreateStateRequest) -> StatePublic:
    d = disease_repo.get_disease(disease_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"disease not found: {disease_id}")

    gene_id = str(d.get("gene_id") or "")
    if not gene_id:
        raise HTTPException(status_code=500, detail="disease.gene_id is missing")
    g = gene_repo.get_gene(gene_id)
    if not g:
        raise HTTPException(status_code=404, detail=f"gene not found: {gene_id}")
    gene_len = int(g.get("length") or 0)
    if gene_len <= 0:
        raise HTTPException(status_code=500, detail=f"invalid gene.length for {gene_id}")

    applied = _validate_request_edits(req, disease_id=disease_id, gene_id=gene_id, gene_len=gene_len)
    row = state_repo.create_state(disease_id, gene_id=gene_id, applied_edit=applied, parent_state_id=req.parent_state_id)

    return StatePublic(
        state_id=str(row.get("state_id")),
        disease_id=str(row.get("disease_id")),
        parent_state_id=row.get("parent_state_id"),
        applied_edit=AppliedEdit.model_validate(row.get("applied_edit") or applied),
        created_at=row.get("created_at"),
    )


def get_state_public(state_id: str) -> StatePublic:
    row = state_repo.get_state(state_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"state not found: {state_id}")

    applied = row.get("applied_edit") or {"type": "user", "edits": []}
    return StatePublic(
        state_id=str(row.get("state_id")),
        disease_id=str(row.get("disease_id")),
        parent_state_id=row.get("parent_state_id"),
        applied_edit=AppliedEdit.model_validate(applied),
        created_at=row.get("created_at"),
    )
