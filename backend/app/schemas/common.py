from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ErrorInfo(BaseModel):
    code: str
    message: str
    detail: Optional[Any] = None


class ErrorEnvelope(BaseModel):
    error: ErrorInfo


class Coordinate(BaseModel):
    coordinate_system: str = Field(default="gene0", description="Coordinate system (gene-local 0-based)")
    assembly: str = Field(default="GRCh38", description="Genome assembly")
    chromosome: Optional[str] = Field(default=None, description="e.g. chr5")
    pos_hg38_1: Optional[int] = Field(default=None, description="1-based hg38 position")
    genomic_position: Optional[str] = Field(default=None, description="e.g. chr5:123456")


class Highlight(BaseModel):
    type: str = Field(description="e.g. 'snv'")
    pos_gene0: int = Field(ge=0)


class UIHints(BaseModel):
    highlight: Highlight
    default_view: str = Field(default="sequence", description="UI default view hint")


class Constraints(BaseModel):
    sequence_alphabet: List[str] = Field(default_factory=lambda: ["A", "C", "G", "T", "N"])
    edit_length_must_be_preserved: bool = Field(default=True, description="substitution only")
    edit_type: str = Field(default="substitution_only", description="Editing policy")
