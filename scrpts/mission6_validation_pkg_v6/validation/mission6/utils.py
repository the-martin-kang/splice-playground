from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

DNA_COMP = str.maketrans("ACGTNacgtn", "TGCANtgcan")

def rc(seq: str) -> str:
    """Reverse-complement (DNA). Keeps N as N."""
    return seq.translate(DNA_COMP)[::-1]

def complement_base(base: str) -> str:
    b = (base or "").strip().upper()
    if len(b) != 1:
        raise ValueError(f"Expected 1 base, got {base!r}")
    return b.translate(DNA_COMP).upper()

def normalize_chrom(chrom: str) -> str:
    """Normalize chrom string to a simple representation (keeps 'chr' if present)."""
    c = str(chrom).strip()
    return c

def with_chr_prefix(chrom: str) -> str:
    c = str(chrom).strip()
    return c if c.lower().startswith("chr") else f"chr{c}"

def without_chr_prefix(chrom: str) -> str:
    c = str(chrom).strip()
    return c[3:] if c.lower().startswith("chr") else c

@dataclass(frozen=True)
class WindowMapping:
    """Maps indices in the 4000bp *transcript-oriented* sequence to genomic coordinates."""
    chrom: str
    pos_1b: int
    strand: str

    def idx_to_genomic_1b(self, idx0: int) -> int:
        """Return 1-based genomic coordinate represented by seq[idx0]."""
        if self.strand == "+":
            # window covers [pos-2000, pos+1999] for '+'
            return (self.pos_1b - 2000) + idx0
        # Mission6 negative-strand fix yields coverage [pos-1999, pos+2000] and mapping:
        # idx0=2000 -> pos
        return (self.pos_1b + 2000) - idx0

    def genomic_1b_to_idx(self, coord_1b: int) -> int:
        """Return 0-based index in seq for a 1-based genomic coord."""
        if self.strand == "+":
            return coord_1b - (self.pos_1b - 2000)
        return (self.pos_1b + 2000) - coord_1b

    def covered_genomic_range_1b(self) -> Tuple[int, int]:
        """Return (min_coord, max_coord) covered by the 4000bp sequence, inclusive."""
        a = self.idx_to_genomic_1b(0)
        b = self.idx_to_genomic_1b(3999)
        return (min(a, b), max(a, b))
