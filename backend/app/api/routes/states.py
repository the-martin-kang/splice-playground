from __future__ import annotations

from fastapi import APIRouter

from app.schemas.state import CreateStateRequest, StatePublic
from app.services.state_service import create_state_for_disease, get_state_public

router = APIRouter(tags=["states"])


@router.post("/diseases/{disease_id}/states", response_model=StatePublic)
def create_state(disease_id: str, req: CreateStateRequest) -> StatePublic:
    return create_state_for_disease(disease_id, req)


@router.get("/states/{state_id}", response_model=StatePublic)
def get_state(state_id: str) -> StatePublic:
    return get_state_public(state_id)
