# app/schemas/common.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SchemaBase(BaseModel):
    """
    Pydantic v2 base schema.
    - populate_by_name: alias 필드(from 등) 사용 시 편함
    - extra=ignore: 서비스에서 필드가 늘어나도 깨지지 않게(초기 개발 안정)
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class APIError(SchemaBase):
    code: str = Field(..., description="Machine-readable error code (e.g. NOT_FOUND)")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[Dict[str, Any]] = Field(default=None, description="Optional structured detail")


class ErrorResponse(SchemaBase):
    error: APIError


class Coordinate(SchemaBase):
    coordinate_system: str = Field("gene0", description="Coordinate system (gene-local 0-based)")
    assembly: str = Field("GRCh38", description="Genome assembly")
    chromosome: Optional[str] = Field(default=None, description="e.g. chr5")
    pos_hg38_1: Optional[int] = Field(default=None, description="1-based hg38 position")
    genomic_position: Optional[str] = Field(default=None, description="e.g. chr5:123456")


class Constraints(SchemaBase):
    sequence_alphabet: List[str] = Field(default_factory=lambda: ["A", "C", "G", "T", "N"])
    edit_length_must_be_preserved: bool = Field(True, description="substitution only")
    edit_type: str = Field("substitution_only", description="Editing policy")


class Highlight(SchemaBase):
    type: str = Field(..., description="e.g. 'snv'")
    pos_gene0: int = Field(..., ge=0)


class UIHints(SchemaBase):
    highlight: Highlight
    default_view: str = Field("sequence", description="UI default view hint")
