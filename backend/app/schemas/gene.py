# app/schemas/gene.py
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.schemas.common import SchemaBase


class Gene(SchemaBase):
    gene_id: str
    gene_symbol: str
    chromosome: Optional[str] = None
    strand: Literal["+", "-"]

    length: int = Field(..., gt=0)
    exon_count: int = Field(..., gt=0)

    canonical_transcript_id: Optional[str] = None
    canonical_source: Optional[str] = None
    source_version: Optional[str] = None
