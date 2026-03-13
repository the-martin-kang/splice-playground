from __future__ import annotations

from typing import List, Optional

from fastapi import HTTPException

from app.db.repositories import disease_repo, gene_repo, region_repo, state_repo, snv_repo
from app.schemas.state import AppliedEdit, CreateStateRequest, StatePublic
from app.services.gene_context import build_gene_sequence, resolve_single_gene_id_for_disease
from app.services.state_lineage import load_parent_chain_edits
from app.services.snv_alleles import to_gene_direction_alleles

_ALLOWED = {"A", "C", "G", "T", "N"}


def _normalize_applied_edit(applied: Optional[AppliedEdit]) -> dict:
    if applied is None:
        return {"type": "user", "edits": []}
    edits = []
    for e in applied.edits:
        edits.append({"pos": int(e.pos_gene0), "from": e.from_base.upper(), "to": e.to_base.upper()})
    return {"type": applied.type, "edits": edits}


def _current_sequence_for_edits(
    disease_id: str,
    disease_row: dict,
    gene_id: str,
    gene_strand: str,
    gene_len: int,
    parent_state_id: Optional[str],
) -> List[str]:
    regions = region_repo.list_regions_by_gene(gene_id, include_sequence=True)
    seq = list(build_gene_sequence(gene_len, regions))

    seed_mode = str(disease_row.get("seed_mode") or "apply_alt")
    rep = snv_repo.get_representative_snv(disease_id)
    if rep is not None and seed_mode != "reference_is_current":
        pos = int(rep["pos_gene0"])
        if 0 <= pos < len(seq):
            _, alt_gene = to_gene_direction_alleles(rep, gene_strand)
            seq[pos] = alt_gene

    for e in load_parent_chain_edits(parent_state_id, disease_id=disease_id):
        pos = e["pos"]
        if 0 <= pos < len(seq):
            seq[pos] = e["to"]
    return seq


def _validate_request_edits(
    req: CreateStateRequest,
    *,
    disease_id: str,
    disease_row: dict,
    gene_id: str,
    gene_strand: str,
    gene_len: int,
) -> dict:
    applied = _normalize_applied_edit(req.applied_edit)
    current_seq = _current_sequence_for_edits(disease_id, disease_row, gene_id, gene_strand, gene_len, req.parent_state_id)

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
                    "hint": "The editor works on the disease sequence already transformed to gene direction; representative SNV may already be applied depending on seed_mode and parent_state_id lineage.",
                },
            )

        cleaned.append({"pos": pos, "from": fb, "to": tb})
        current_seq[pos] = tb
    return {"type": applied["type"], "edits": cleaned}


def create_state_for_disease(disease_id: str, req: CreateStateRequest) -> StatePublic:
    disease = disease_repo.get_disease(disease_id)
    if not disease:
        raise HTTPException(status_code=404, detail=f"disease not found: {disease_id}")

    try:
        gene_id = resolve_single_gene_id_for_disease(disease_id, disease)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    gene = gene_repo.get_gene(gene_id)
    if not gene:
        raise HTTPException(status_code=404, detail=f"gene not found: {gene_id}")

    gene_len = int(gene.get("length") or 0)
    if gene_len <= 0:
        raise HTTPException(status_code=500, detail=f"invalid gene.length for {gene_id}")
    gene_strand = str(gene.get("strand") or "+")

    applied = _validate_request_edits(
        req,
        disease_id=disease_id,
        disease_row=disease,
        gene_id=gene_id,
        gene_strand=gene_strand,
        gene_len=gene_len,
    )
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
