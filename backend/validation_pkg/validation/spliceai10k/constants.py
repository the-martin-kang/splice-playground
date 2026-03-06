from __future__ import annotations

from dataclasses import dataclass

# Default SpliceAI-10k style lengths
IN_LENGTH_DEFAULT: int = 15000   # input length fed to the model
OUT_LENGTH_DEFAULT: int = 5000   # central core length we keep for scoring/plots

# Canonical splice motifs (DNA alphabet)
CANONICAL_DONOR_MOTIFS = ("GT", "GC")  # GU (or rare GC) in RNA, but FASTA uses T
CANONICAL_ACCEPTOR_MOTIF = "AG"


def center_index(length: int) -> int:
    """0-based center index (even -> right center)."""
    return int(length // 2)


def core_slice(in_length: int, out_length: int) -> slice:
    """Return slice selecting the centered out_length region from an in_length array."""
    if out_length > in_length:
        raise ValueError(f"out_length({out_length}) must be <= in_length({in_length})")
    start = int((in_length - out_length) // 2)
    end = start + int(out_length)
    return slice(start, end)
