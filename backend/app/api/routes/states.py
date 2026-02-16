# app/api/routes/states.py
from __future__ import annotations

from fastapi import APIRouter

from app.schemas.state import CreateStateRequest, CreateStateResponse
from app.services.state_service import StateService

router = APIRouter(tags=["states"])


@router.post("/diseases/{disease_id}/states", response_model=CreateStateResponse)
def create_state(
    disease_id: str,
    req: CreateStateRequest,
) -> CreateStateResponse:
    applied_edit = req.applied_edit.model_dump(by_alias=True)
    return StateService.create_state(
        disease_id=disease_id,
        applied_edit=applied_edit,
        parent_state_id=req.parent_state_id,
    )
