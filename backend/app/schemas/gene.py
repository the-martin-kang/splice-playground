from __future__ import annotations

from typing import Optional, Literal

from pydantic import BaseModel, Field


class Gene(BaseModel):
    gene_id: str
    gene_symbol: str
    chromosome: Optional[str] = None
    strand: Literal["+", "-"] = "+"
    length: int = Field(gt=0)
    exon_count: int = Field(gt=0)

    canonical_transcript_id: Optional[str] = None
    canonical_source: Optional[str] = None
    source_version: Optional[str] = None
