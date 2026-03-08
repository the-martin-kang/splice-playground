
from __future__ import annotations

from typing import Dict, Tuple

_COMP = {"A": "T", "T": "A", "C": "G", "G": "C", "N": "N"}


def complement_base(b: str) -> str:
    return _COMP.get((b or "N").upper(), "N")


def to_gene_direction_alleles(snv_row: Dict, gene_strand: str) -> Tuple[str, str]:
    """Return (ref, alt) oriented to the gene/transcript 5'->3' direction.

    Supported coordinate systems:
      - gene_direction (default/legacy): stored ref/alt already match gene-local sequence
      - genomic_positive: stored ref/alt follow genomic + strand (VCF/ClinVar style)
        -> complement when gene strand is '-'
    """
    ref = str(snv_row.get("ref") or "N").upper()
    alt = str(snv_row.get("alt") or "N").upper()
    coord = str(snv_row.get("allele_coordinate_system") or "gene_direction").strip().lower()
    strand = str(gene_strand or "+").strip()

    if coord in {"genomic_positive", "genomic", "positive_strand", "plus_strand"}:
        if strand == "-":
            return complement_base(ref), complement_base(alt)
        return ref, alt

    # gene_direction / legacy
    return ref, alt
