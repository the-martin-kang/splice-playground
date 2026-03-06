from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class Edit(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pos_gene0: int = Field(alias="pos", ge=0)
    from_base: str = Field(alias="from", min_length=1, max_length=1)
    to_base: str = Field(alias="to", min_length=1, max_length=1)


class AppliedEdit(BaseModel):
    type: str = "user"
    edits: List[Edit] = Field(default_factory=list)


class CreateStateRequest(BaseModel):
    applied_edit: Optional[AppliedEdit] = None
    parent_state_id: Optional[str] = None


class StatePublic(BaseModel):
    state_id: str
    disease_id: str
    parent_state_id: Optional[str] = None
    applied_edit: AppliedEdit
    created_at: Optional[str] = None
