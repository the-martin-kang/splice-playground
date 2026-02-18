from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .constants import CANONICAL_ACCEPTOR_MOTIF, CANONICAL_DONOR_MOTIFS
from .utils import WindowMapping


@dataclass
class SiteCall:
    kind: str  # 'donor' or 'acceptor'
    idx0: int  # 0-based index in 4000 seq (transcript-oriented)
    genomic_1b: int
    prob: float
    motif: Optional[str] = None
    snapped_from_idx0: Optional[int] = None
    nearest_annot_1b: Optional[int] = None
    delta_to_nearest_annot: Optional[int] = None


def _motif_at(seq: str, idx0: int, kind: str) -> Optional[str]:
    """Return motif string at idx0 according to canonical conventions."""
    if kind == "donor":
        if 0 <= idx0 <= len(seq) - 2:
            return seq[idx0 : idx0 + 2]
        return None
    if kind == "acceptor":
        if 2 <= idx0 <= len(seq):
            return seq[idx0 - 2 : idx0]
        return None
    raise ValueError("kind must be donor/acceptor")


def snap_to_canonical_motif(
    seq: str,
    probs: np.ndarray,
    mapping: WindowMapping,
    kind: str,
    idx0: int,
    max_shift: int = 5,
) -> SiteCall:
    """Snap a predicted site index to the nearest canonical motif within ±max_shift.

    Strategy: among candidate indices that have canonical motif, choose the one with max prob.
    If none found, keep original index.

    probs: shape (L,) for the corresponding channel.
    """
    L = len(seq)
    best_idx = idx0
    best_prob = float(probs[idx0]) if 0 <= idx0 < L else float("nan")

    def is_canonical(m: Optional[str]) -> bool:
        if not m:
            return False
        if kind == "donor":
            return m in CANONICAL_DONOR_MOTIFS
        return m == CANONICAL_ACCEPTOR_MOTIF

    candidates: List[int] = []
    for d in range(-max_shift, max_shift + 1):
        j = idx0 + d
        if not (0 <= j < L):
            continue
        m = _motif_at(seq, j, kind)
        if is_canonical(m):
            candidates.append(j)

    snapped_from = None
    if candidates:
        # choose highest prob among candidates
        snapped_from = idx0
        best_idx = max(candidates, key=lambda j: float(probs[j]))
        best_prob = float(probs[best_idx])

    genomic = mapping.idx_to_genomic_1b(best_idx)
    motif = _motif_at(seq, best_idx, kind)

    return SiteCall(
        kind=kind,
        idx0=best_idx,
        genomic_1b=int(genomic),
        prob=float(best_prob),
        motif=motif,
        snapped_from_idx0=snapped_from,
    )


def nearest_site(coord_1b: int, sites_1b: List[int]) -> Tuple[Optional[int], Optional[int]]:
    """Return (nearest_site, delta=coord-site)."""
    if not sites_1b:
        return None, None
    nearest = min(sites_1b, key=lambda x: abs(int(x) - int(coord_1b)))
    return int(nearest), int(coord_1b) - int(nearest)


def summarize_sites(
    seq_ref: str,
    prob_ref: np.ndarray,
    mapping: WindowMapping,
    donor_sites_1b: List[int],
    acceptor_sites_1b: List[int],
    top_k: int = 5,
    snap_k: int = 5,
    donor_channel: int = 1,
    acceptor_channel: int = 2,
) -> Dict[str, List[SiteCall]]:
    """Create top-k predicted site calls with optional motif snapping and nearest annotation mapping."""
    L = len(seq_ref)
    donor_probs = prob_ref[donor_channel]
    acceptor_probs = prob_ref[acceptor_channel]

    # get top indices (excluding edges where motif can't be evaluated)
    donor_candidates = np.argsort(-donor_probs)[: top_k * 3]  # take more before filtering
    acceptor_candidates = np.argsort(-acceptor_probs)[: top_k * 3]

    donor_calls: List[SiteCall] = []
    for i in donor_candidates:
        i = int(i)
        call = snap_to_canonical_motif(seq_ref, donor_probs, mapping, "donor", i, max_shift=snap_k)
        # annotate nearest
        near, delta = nearest_site(call.genomic_1b, donor_sites_1b)
        call.nearest_annot_1b = near
        call.delta_to_nearest_annot = delta
        donor_calls.append(call)
        if len(donor_calls) >= top_k:
            break

    acceptor_calls: List[SiteCall] = []
    for i in acceptor_candidates:
        i = int(i)
        call = snap_to_canonical_motif(seq_ref, acceptor_probs, mapping, "acceptor", i, max_shift=snap_k)
        near, delta = nearest_site(call.genomic_1b, acceptor_sites_1b)
        call.nearest_annot_1b = near
        call.delta_to_nearest_annot = delta
        acceptor_calls.append(call)
        if len(acceptor_calls) >= top_k:
            break

    return {"donor": donor_calls, "acceptor": acceptor_calls}
