from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pyfaidx import Fasta

from .utils import rc, with_chr_prefix, without_chr_prefix


@dataclass
class ReferenceGenome:
    """Reference FASTA reader with Mission6-compatible fetch semantics."""

    fasta_path: str
    as_raw: bool = True
    sequence_always_upper: bool = True

    def __post_init__(self) -> None:
        # pyfaidx will create .fai if missing
        self.fa = Fasta(self.fasta_path, as_raw=self.as_raw, sequence_always_upper=self.sequence_always_upper)
        self._keys = set(self.fa.keys())
        # detect whether fasta keys use 'chr' prefix
        self._has_chr = any(k.startswith("chr") for k in list(self._keys)[:10])

    def _normalize_key(self, chrom: str) -> str:
        c = str(chrom).strip()
        if self._has_chr:
            c = with_chr_prefix(c)
        else:
            c = without_chr_prefix(c)
        if c not in self._keys:
            # try toggling prefix once more
            alt = without_chr_prefix(c) if c.startswith("chr") else with_chr_prefix(c)
            if alt in self._keys:
                return alt
            raise KeyError(f"Chromosome {chrom!r} not found in FASTA. Example keys: {sorted(list(self._keys))[:5]}")
        return c

    def fetch_seq(self, chrom: str, start0: int, end0: int, strand: str = "+") -> str:
        """Fetch 0-based half-open [start0, end0) and apply Mission6 '-' shift + reverse-complement.

        IMPORTANT: Mission6 notebook applied an off-by-one fix for negative strand:
          if strand == '-', we shift start and end by +1 BEFORE slicing, then reverse-complement.
        """
        if start0 < 0:
            raise ValueError("start0 must be >= 0 (clip before calling fetch_seq)")
        if end0 < start0:
            raise ValueError("end0 must be >= start0")

        key = self._normalize_key(chrom)

        if strand == "-":
            start0 += 1
            end0 += 1

        seq = str(self.fa[key][start0:end0]).upper()

        if strand == "-":
            seq = rc(seq)
        return seq
