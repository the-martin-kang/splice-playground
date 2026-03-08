# app/utils/alleles.py
from __future__ import annotations

from typing import Literal

AlleleCoordinateSystem = Literal["gene_direction", "genomic_positive"]

_COMP = str.maketrans({
    "A": "T",
    "T": "A",
    "C": "G",
    "G": "C",
    "N": "N",
})


def normalize_base(base: str) -> str:
    s = (base or "").strip().upper()
    if len(s) != 1 or s not in {"A", "C", "G", "T", "N"}:
        raise ValueError(f"Invalid DNA base: {base!r}")
    return s


def complement_base(base: str) -> str:
    return normalize_base(base).translate(_COMP)


def to_gene_direction(
    base: str,
    *,
    strand: str,
    allele_coordinate_system: str | None,
) -> str:
    """
    Convert stored allele to gene-direction allele.

    - gene_direction: 그대로 사용
    - genomic_positive:
        + strand -> 그대로
        - strand -> complement
    """
    b = normalize_base(base)
    mode = (allele_coordinate_system or "gene_direction").strip().lower()

    if mode == "gene_direction":
        return b
    if mode == "genomic_positive":
        return b if strand == "+" else complement_base(b)

    raise ValueError(f"Unknown allele_coordinate_system: {allele_coordinate_system!r}")