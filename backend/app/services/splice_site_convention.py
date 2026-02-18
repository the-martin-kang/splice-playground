# app/services/splice_site_convention.py
from __future__ import annotations

from typing import Literal, Optional, Tuple

DonorLabelMode = Literal["exon_end", "intron_start"]

CANONICAL_DONOR_MOTIFS = {"GT", "GC"}
CANONICAL_ACCEPTOR_MOTIF = "AG"


def acceptor_motif(seq: str, label_idx0: int) -> Optional[str]:
    """acceptor label = exon start -> motif is immediately BEFORE label: seq[idx0-2:idx0]."""
    if label_idx0 < 2 or label_idx0 > len(seq):
        return None
    return seq[label_idx0 - 2 : label_idx0]


def donor_motif(seq: str, label_idx0: int, donor_label_mode: DonorLabelMode = "exon_end") -> Optional[str]:
    """donor motif relative to label position.

    - exon_end  : label at last exon base -> motif is AFTER label: seq[idx0+1:idx0+3]
    - intron_start: label at first intron base -> motif starts at label: seq[idx0:idx0+2]
    """
    L = len(seq)
    if donor_label_mode == "exon_end":
        if label_idx0 < 0 or label_idx0 + 3 > L:
            return None
        return seq[label_idx0 + 1 : label_idx0 + 3]

    # intron_start
    if label_idx0 < 0 or label_idx0 + 2 > L:
        return None
    return seq[label_idx0 : label_idx0 + 2]


def acceptor_cut(label_idx0: int) -> Tuple[int, int]:
    """Cut is between (idx0-1) | (idx0)."""
    return label_idx0 - 1, label_idx0


def donor_cut(label_idx0: int, donor_label_mode: DonorLabelMode = "exon_end") -> Tuple[int, int]:
    """Cut edge implied by donor label position."""
    if donor_label_mode == "exon_end":
        # cut between (idx0) | (idx0+1)
        return label_idx0, label_idx0 + 1
    # intron_start
    return label_idx0 - 1, label_idx0


def is_canonical_acceptor(seq: str, label_idx0: int) -> bool:
    return acceptor_motif(seq, label_idx0) == CANONICAL_ACCEPTOR_MOTIF


def is_canonical_donor(seq: str, label_idx0: int, donor_label_mode: DonorLabelMode = "exon_end") -> bool:
    m = donor_motif(seq, label_idx0, donor_label_mode=donor_label_mode)
    return m in CANONICAL_DONOR_MOTIFS if m else False
