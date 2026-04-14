from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.core.config import get_settings
from app.db.repositories.step4_baseline_repo import list_structure_assets
from app.db.repositories.structure_job_repo import create_job, get_job, list_jobs_for_state
from app.schemas.step4 import CreateStep4StructureJobRequest, Step4StructureJobCreateResponse
from app.services.protein_translation import sha256_text
from app.services.step4_state_service import _job_public, get_step4_for_state


ACTIVE_STATUSES = {"queued", "running"}
TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}


def _prediction_disabled_message() -> str:
    return (
        "STEP4 structure prediction jobs are disabled on this backend right now. "
        "The normal baseline structure is already available for Mol*; later, enable "
        "STEP4_ENABLE_STRUCTURE_JOBS=true on the public API server and start the ColabFold worker on the GPU host."
    )


def _result_payload_sha(row: Dict[str, Any]) -> Optional[str]:
    payload = row.get("result_payload") or {}
    sha = payload.get("user_protein_sha256")
    return str(sha) if sha else None


def _find_existing_job(
    *,
    state_id: str,
    provider: str,
    user_protein_sha256: str,
    allow_terminal: bool = True,
) -> Optional[Dict[str, Any]]:
    for row in list_jobs_for_state(state_id, include_payload=True):
        if str(row.get("provider") or "") != provider:
            continue
        if _result_payload_sha(row) != user_protein_sha256:
            continue
        status = str(row.get("status") or "")
        if status in ACTIVE_STATUSES:
            return row
        if allow_terminal and status in TERMINAL_STATUSES:
            return row
    return None


def _baseline_reuse_payload(step4_state) -> Dict[str, Any]:
    baseline_protein = step4_state.normal_track.baseline_protein
    structure_rows = list_structure_assets(str(baseline_protein.protein_reference_id))
    assets: List[Dict[str, Any]] = []
    for row in structure_rows:
        assets.append(
            {
                "kind": "structure",
                "bucket": str(row.get("storage_bucket") or ""),
                "path": str(row.get("storage_path") or ""),
                "file_format": str(row.get("file_format") or "cif"),
                "name": Path(str(row.get("storage_path") or "")).name or None,
                "source_db": row.get("source_db"),
                "source_id": row.get("source_id"),
                "source_chain_id": row.get("source_chain_id"),
                "is_default": bool(row.get("is_default")),
            }
        )
    return {
        "user_protein_sha256": sha256_text(step4_state.user_track.protein_seq or step4_state.normal_track.baseline_protein.protein_seq or ""),
        "user_protein_length": step4_state.user_track.comparison_to_normal.user_protein_length,
        "reused_baseline_structure": True,
        "comparison_to_normal": step4_state.user_track.comparison_to_normal.model_dump(),
        "confidence": {"strategy": "reuse_baseline_structure"},
        "assets": assets,
        "baseline_default_structure_asset_id": step4_state.normal_track.default_structure_asset_id,
    }


def _queued_colabfold_payload(step4_state) -> Dict[str, Any]:
    baseline_protein = step4_state.normal_track.baseline_protein
    structure_rows = list_structure_assets(str(baseline_protein.protein_reference_id))
    default_row = next((r for r in structure_rows if bool(r.get("is_default"))), None)
    if default_row is None and structure_rows:
        default_row = structure_rows[0]

    baseline_default_structure = None
    if default_row is not None:
        baseline_default_structure = {
            "structure_asset_id": default_row.get("structure_asset_id"),
            "bucket": default_row.get("storage_bucket"),
            "path": default_row.get("storage_path"),
            "file_format": default_row.get("file_format"),
            "source_db": default_row.get("source_db"),
            "source_id": default_row.get("source_id"),
            "source_chain_id": default_row.get("source_chain_id"),
        }

    transcript = step4_state.user_track.predicted_transcript
    translation = step4_state.user_track.translation_sanity
    comparison = step4_state.user_track.comparison_to_normal

    return {
        "gene_id": step4_state.gene_id,
        "disease_id": step4_state.disease_id,
        "state_id": step4_state.state_id,
        "user_protein_seq": step4_state.user_track.protein_seq or "",
        "user_protein_sha256": sha256_text(step4_state.user_track.protein_seq or ""),
        "user_protein_length": comparison.user_protein_length,
        "comparison_to_normal": comparison.model_dump(),
        "translation_sanity": {
            "translation_ok": translation.translation_ok,
            "reason": translation.reason,
            "protein_length": translation.protein_length,
            "cds_length_nt": translation.cds_length_nt,
            "start_codon_preserved": translation.start_codon_preserved,
            "stop_codon_found": translation.stop_codon_found,
            "frameshift_likely": translation.frameshift_likely,
            "premature_stop_likely": translation.premature_stop_likely,
            "notes": list(translation.notes or []),
        },
        "predicted_transcript": {
            "primary_event_type": transcript.primary_event_type,
            "primary_subtype": transcript.primary_subtype,
            "included_exon_numbers": list(transcript.included_exon_numbers),
            "excluded_exon_numbers": list(transcript.excluded_exon_numbers),
            "inserted_block_count": transcript.inserted_block_count,
            "warnings": list(transcript.warnings or []),
        },
        "reused_baseline_structure": False,
        "normal_protein_sha256": sha256_text(baseline_protein.protein_seq or ""),
        "normal_protein_length": baseline_protein.protein_length,
        "baseline_protein_reference_id": baseline_protein.protein_reference_id,
        "baseline_default_structure_asset_id": step4_state.normal_track.default_structure_asset_id,
        "baseline_default_structure": baseline_default_structure,
        "confidence": {},
        "assets": [],
    }


def create_step4_structure_job(state_id: str, req: CreateStep4StructureJobRequest) -> Step4StructureJobCreateResponse:
    settings = get_settings()
    step4_state = get_step4_for_state(state_id, include_sequences=True, hydrate_jobs=False, include_latest_job_payload=False)

    if not settings.STEP4_ENABLE_STRUCTURE_JOBS:
        return Step4StructureJobCreateResponse(
            created=False,
            reused_baseline_structure=False,
            message=_prediction_disabled_message(),
            job=None,
            user_track=step4_state.user_track,
        )

    user_protein_seq = step4_state.user_track.protein_seq or ""
    if not user_protein_seq:
        raise HTTPException(status_code=400, detail="STEP4 user protein sequence is empty; create STEP4 state first and inspect translation sanity.")

    user_protein_sha = sha256_text(user_protein_seq)

    if step4_state.user_track.can_reuse_normal_structure and req.reuse_if_identical:
        existing = None if req.force else _find_existing_job(
            state_id=state_id,
            provider="baseline_reuse",
            user_protein_sha256=user_protein_sha,
            allow_terminal=True,
        )
        if existing:
            return Step4StructureJobCreateResponse(
                created=False,
                reused_baseline_structure=True,
                message="Baseline structure reuse job already exists for this user protein.",
                job=_job_public(existing),
                user_track=step4_state.user_track,
            )
        row = create_job(
            state_id=state_id,
            provider="baseline_reuse",
            status="succeeded",
            result_payload=_baseline_reuse_payload(step4_state),
        )
        return Step4StructureJobCreateResponse(
            created=True,
            reused_baseline_structure=True,
            message="User protein matches the normal protein; baseline structures are reused.",
            job=_job_public(row),
            user_track=step4_state.user_track,
        )

    provider = str(req.provider)
    existing = None if req.force else _find_existing_job(
        state_id=state_id,
        provider=provider,
        user_protein_sha256=user_protein_sha,
        allow_terminal=True,
    )
    if existing:
        status = str(existing.get("status") or "unknown")
        message = (
            "A STEP4 structure job with the same provider and user protein already exists."
            if status in TERMINAL_STATUSES
            else "A matching STEP4 structure job is already queued or running."
        )
        return Step4StructureJobCreateResponse(
            created=False,
            reused_baseline_structure=False,
            message=message,
            job=_job_public(existing),
            user_track=step4_state.user_track,
        )

    row = create_job(
        state_id=state_id,
        provider=provider,
        status="queued",
        result_payload=_queued_colabfold_payload(step4_state),
    )
    return Step4StructureJobCreateResponse(
        created=True,
        reused_baseline_structure=False,
        message="STEP4 structure prediction job queued.",
        job=_job_public(row),
        user_track=step4_state.user_track,
    )


def get_step4_structure_job(job_id: str, *, include_payload: bool = False):
    row = get_job(job_id, include_payload=include_payload)
    if not row:
        raise HTTPException(status_code=404, detail=f"structure_job not found: {job_id}")
    return _job_public(row)
