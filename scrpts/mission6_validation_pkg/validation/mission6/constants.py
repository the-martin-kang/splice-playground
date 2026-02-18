from __future__ import annotations

IN_LENGTH: int = 4000
"""Input sequence length (Mission6 uses 4000)."""

CENTER_INDEX: int = IN_LENGTH // 2  # 2000
"""0-based index of the variant position in the 4000bp input."""

# In the Mission6 notebook, scoring uses the central 2000 positions: [1000, 3000)
SCORE_CENTER_SLICE = slice(1000, 3000)

CANONICAL_DONOR_MOTIFS = ("GT", "GC")  # GU (or rare GC) in DNA alphabet
CANONICAL_ACCEPTOR_MOTIF = "AG"
