from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.schemas.step4 import (
    CreateStep4StructureJobRequest,
    Step4BaselineResponse,
    Step4CapabilitiesPublic,
    Step4MolstarTargetPublic,
    Step4StateResponse,
    Step4StructureAssetPublic,
    Step4StructureJobCreateResponse,
    Step4StructureJobPublic,
)
from app.services.step4_baseline_service import (
    get_step4_baseline_for_disease,
    get_step4_baseline_for_state,
)
from app.services.step4_state_service import get_step4_for_state
from app.services.structure_job_service import create_step4_structure_job, get_step4_structure_job


router = APIRouter(tags=["step4"])


def _viewer_format(file_format: Optional[str]) -> Optional[str]:
    fmt = str(file_format or "").strip().lower()
    if not fmt:
        return None
    if fmt in {"cif", "mmcif"}:
        return "mmcif"
    if fmt == "bcif":
        return "bcif"
    if fmt == "pdb":
        return "pdb"
    return fmt


def _pick_default_structure(structures: list[Step4StructureAssetPublic]) -> Optional[Step4StructureAssetPublic]:
    if not structures:
        return None
    for asset in structures:
        if asset.is_default:
            return asset
    return structures[0]


def _molstar_target(asset: Optional[Step4StructureAssetPublic]) -> Optional[Step4MolstarTargetPublic]:
    if not asset or not asset.signed_url:
        return None
    return Step4MolstarTargetPublic(
        structure_asset_id=asset.structure_asset_id,
        provider=asset.provider,
        source_db=asset.source_db,
        source_id=asset.source_id,
        source_chain_id=asset.source_chain_id,
        title=asset.title,
        url=asset.signed_url,
        format=asset.viewer_format or _viewer_format(asset.file_format),
    )


def _normalize_structures(structures: list[Step4StructureAssetPublic]) -> list[Step4StructureAssetPublic]:
    out: list[Step4StructureAssetPublic] = []
    for asset in structures:
        out.append(asset.model_copy(update={"viewer_format": _viewer_format(asset.file_format)}))
    return out


def _prediction_disabled_reason() -> str:
    return (
        "STEP4 user-structure prediction jobs are disabled on this CPU-only deployment. "
        "Normal baseline structures are fully available now; later, turn on STEP4_ENABLE_STRUCTURE_JOBS "
        "on the GPU-backed deployment to queue ColabFold jobs."
    )


def _enrich_baseline(resp: Step4BaselineResponse) -> Step4BaselineResponse:
    settings = get_settings()
    structures = _normalize_structures(list(resp.structures or []))
    default_asset = _pick_default_structure(structures)
    ready = bool(default_asset and default_asset.signed_url)
    capabilities = Step4CapabilitiesPublic(
        normal_structure_ready=ready,
        user_track_available=bool(resp.state_id),
        structure_prediction_enabled=bool(settings.STEP4_ENABLE_STRUCTURE_JOBS),
        create_job_endpoint_enabled=bool(settings.STEP4_ENABLE_STRUCTURE_JOBS and resp.state_id),
        prediction_mode=("job_queue" if settings.STEP4_ENABLE_STRUCTURE_JOBS else "disabled"),
        reason=(None if settings.STEP4_ENABLE_STRUCTURE_JOBS else _prediction_disabled_reason()),
    )
    notes = list(resp.notes or [])
    if capabilities.reason:
        notes.append(capabilities.reason)
    return resp.model_copy(
        update={
            "structures": structures,
            "default_structure_asset_id": (default_asset.structure_asset_id if default_asset else resp.default_structure_asset_id),
            "default_structure": default_asset,
            "molstar_default": _molstar_target(default_asset),
            "capabilities": capabilities,
            "ready_for_frontend": ready,
            "notes": notes,
        }
    )


@router.get("/diseases/{disease_id}/step4-baseline", response_model=Step4BaselineResponse)
def get_disease_step4_baseline(
    disease_id: str,
    include_sequences: bool = Query(False, description="Return canonical mRNA / CDS / protein sequence strings"),
) -> Step4BaselineResponse:
    return _enrich_baseline(get_step4_baseline_for_disease(disease_id, include_sequences=include_sequences))


@router.get("/states/{state_id}/step4-baseline", response_model=Step4BaselineResponse)
def get_state_step4_baseline(
    state_id: str,
    include_sequences: bool = Query(False, description="Return canonical mRNA / CDS / protein sequence strings"),
) -> Step4BaselineResponse:
    return _enrich_baseline(get_step4_baseline_for_state(state_id, include_sequences=include_sequences))


@router.get("/states/{state_id}/step4", response_model=Step4StateResponse)
def get_state_step4(
    state_id: str,
    include_sequences: bool = Query(False, description="Return user-track cDNA / CDS / protein sequences and normal protein sequence strings"),
) -> Step4StateResponse:
    return get_step4_for_state(state_id, include_sequences=include_sequences)


@router.post("/states/{state_id}/step4/jobs", response_model=Step4StructureJobCreateResponse)
def post_state_step4_job(
    state_id: str,
    body: CreateStep4StructureJobRequest,
) -> Step4StructureJobCreateResponse:
    return create_step4_structure_job(state_id, body)


@router.get("/step4-jobs/{job_id}", response_model=Step4StructureJobPublic)
def get_step4_job(job_id: str) -> Step4StructureJobPublic:
    return get_step4_structure_job(job_id)
