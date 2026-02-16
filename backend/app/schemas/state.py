# app/schemas/state.py
from __future__ import annotations

from typing import List, Optional

from pydantic import Field, field_validator, model_validator

from app.schemas.common import SchemaBase

_ALLOWED_BASES = {"A", "C", "G", "T", "N"}


class EditItem(SchemaBase):
    pos: int = Field(..., ge=0)
    from_base: str = Field(..., alias="from", min_length=1, max_length=1)
    to: str = Field(..., min_length=1, max_length=1)

    @field_validator("from_base", "to", mode="before")
    @classmethod
    def _norm_base(cls, v):
        if v is None:
            return v
        s = str(v).strip().upper()
        return s

    @model_validator(mode="after")
    def _check(self):
        if self.from_base not in _ALLOWED_BASES or self.to not in _ALLOWED_BASES:
            raise ValueError(f"bases must be one of {_ALLOWED_BASES}")
        if self.from_base == self.to:
            raise ValueError("from and to must differ")
        return self


class AppliedEdit(SchemaBase):
    type: str = Field(..., min_length=1)
    edits: List[EditItem] = Field(default_factory=list)


class CreateStateRequest(SchemaBase):
    parent_state_id: Optional[str] = None
    applied_edit: AppliedEdit


class CreateStateResponse(SchemaBase):
    state_id: str
