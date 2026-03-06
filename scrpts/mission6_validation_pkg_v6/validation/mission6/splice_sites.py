from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .constants import CANONICAL_ACCEPTOR_MOTIF, CANONICAL_DONOR_MOTIFS
from .utils import WindowMapping


@dataclass
class SiteCall:
    """A predicted splice site call.

    Important conventions (Mission6 / your preprocessing):
      - acceptor label: exon START (first exon base in transcript direction)
        => canonical motif AG is immediately BEFORE the label position: seq[idx0-2:idx0]
        => cut (junction) is between (idx0-1) | (idx0)

      - donor label: exon END (last exon base in transcript direction)  [recommended]
        => canonical motif GT/GC is immediately AFTER the label position: seq[idx0+1:idx0+3]
        => cut (junction) is between (idx0) | (idx0+1)

    For backward compatibility, we still support donor_label_mode='intron_start'
    (donor label at first intron base).
    """

    kind: str  # 'donor' or 'acceptor'
    idx0: int  # 0-based index in 4000 seq (transcript-oriented)
    genomic_1b: int  # genomic coordinate for seq[idx0]
    prob: float

    motif: Optional[str] = None
    snapped_from_idx0: Optional[int] = None

    # Junction (cut) represented as between two indices in transcript-oriented sequence
    cut_left_idx0: Optional[int] = None
    cut_right_idx0: Optional[int] = None
    cut_left_genomic_1b: Optional[int] = None
    cut_right_genomic_1b: Optional[int] = None

    # Nearest annotation label site (1-based genomic)
    nearest_annot_1b: Optional[int] = None
    delta_to_nearest_annot: Optional[int] = None


def _motif_at(seq: str, idx0: int, kind: str, donor_label_mode: str) -> Optional[str]:
    """Return motif string around idx0 according to label convention."""
    L = len(seq)

    if kind == "acceptor":
        # acceptor label at exon start -> AG immediately before label
        if 2 <= idx0 <= L:
            return seq[idx0 - 2 : idx0]
        return None

    if kind == "donor":
        if donor_label_mode not in {"exon_end", "intron_start"}:
            raise ValueError("donor_label_mode must be 'exon_end' or 'intron_start'")

        if donor_label_mode == "exon_end":
            # donor label at exon end -> GT/GC immediately after label
            # motif uses indices (idx0+1, idx0+2)
            if 0 <= idx0 <= L - 3:
                return seq[idx0 + 1 : idx0 + 3]
            return None

        # intron_start: donor label at first intron base -> GT/GC starts at label
        if 0 <= idx0 <= L - 2:
            return seq[idx0 : idx0 + 2]
        return None

    raise ValueError("kind must be donor/acceptor")


def _cut_edges_idx0(seq_len: int, idx0: int, kind: str, donor_label_mode: str) -> Tuple[Optional[int], Optional[int]]:
    """Return (left_idx0, right_idx0) for the splice junction (cut) implied by this label."""
    if kind == "acceptor":
        # cut is between (idx0-1) | (idx0)
        if idx0 - 1 < 0 or idx0 >= seq_len:
            return None, None
        return idx0 - 1, idx0

    if kind == "donor":
        if donor_label_mode not in {"exon_end", "intron_start"}:
            raise ValueError("donor_label_mode must be 'exon_end' or 'intron_start'")

        if donor_label_mode == "exon_end":
            # cut is between (idx0) | (idx0+1)
            if idx0 < 0 or idx0 + 1 >= seq_len:
                return None, None
            return idx0, idx0 + 1

        # intron_start: cut is between (idx0-1) | (idx0)
        if idx0 - 1 < 0 or idx0 >= seq_len:
            return None, None
        return idx0 - 1, idx0

    raise ValueError("kind must be donor/acceptor")


def snap_to_canonical_motif(
    seq: str,
    probs: np.ndarray,
    mapping: WindowMapping,
    kind: str,
    idx0: int,
    max_shift: int = 5,
    donor_label_mode: str = "exon_end",
) -> SiteCall:
    """Snap a predicted site index to the nearest canonical motif within ±max_shift.

    Strategy: among candidate indices that have canonical motif, choose the one with max prob.
    If none found, keep original index.
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
        m = _motif_at(seq, j, kind, donor_label_mode=donor_label_mode)
        if is_canonical(m):
            candidates.append(j)

    snapped_from: Optional[int] = None
    if candidates:
        snapped_from = idx0
        best_idx = max(candidates, key=lambda j: float(probs[j]))
        best_prob = float(probs[best_idx])

    genomic = mapping.idx_to_genomic_1b(best_idx)
    motif = _motif_at(seq, best_idx, kind, donor_label_mode=donor_label_mode)

    cut_l, cut_r = _cut_edges_idx0(L, best_idx, kind, donor_label_mode=donor_label_mode)
    cut_l_g: Optional[int] = None
    cut_r_g: Optional[int] = None
    if cut_l is not None and cut_r is not None:
        cut_l_g = int(mapping.idx_to_genomic_1b(cut_l))
        cut_r_g = int(mapping.idx_to_genomic_1b(cut_r))

    return SiteCall(
        kind=kind,
        idx0=int(best_idx),
        genomic_1b=int(genomic),
        prob=float(best_prob),
        motif=motif,
        snapped_from_idx0=snapped_from,
        cut_left_idx0=cut_l,
        cut_right_idx0=cut_r,
        cut_left_genomic_1b=cut_l_g,
        cut_right_genomic_1b=cut_r_g,
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
    *,
    donor_kind_by_1b: Optional[Dict[int, str]] = None,
    acceptor_kind_by_1b: Optional[Dict[int, str]] = None,
    donor_label_mode: str = "exon_end",
    top_k: int = 5,
    snap_k: int = 5,
    donor_channel: int = 2,
    acceptor_channel: int = 1,
) -> Dict[str, List[SiteCall]]:
    """Create top-k predicted site calls with optional motif snapping and nearest annotation mapping.

    Improvements vs earlier version:
      - De-duplicate calls that snap to the same idx0 (keep max prob).
      - Optionally rewrite `kind` to stable exon-based labels (exon{n}_donor / exon{n}_acceptor)
        using donor_kind_by_1b / acceptor_kind_by_1b keyed by nearest_annot_1b.
    """
    donor_probs = prob_ref[donor_channel]
    acceptor_probs = prob_ref[acceptor_channel]

    # take more candidates than top_k to survive snapping + de-dupe
    take_n = min(len(donor_probs), max(top_k * 50, 50))
    donor_candidates = np.argsort(-donor_probs)[:take_n]

    take_n2 = min(len(acceptor_probs), max(top_k * 50, 50))
    acceptor_candidates = np.argsort(-acceptor_probs)[:take_n2]

    donor_by_idx: Dict[int, SiteCall] = {}
    for i in donor_candidates:
        i = int(i)
        call = snap_to_canonical_motif(
            seq_ref,
            donor_probs,
            mapping,
            "donor",
            i,
            max_shift=snap_k,
            donor_label_mode=donor_label_mode,
        )
        near, delta = nearest_site(call.genomic_1b, donor_sites_1b)
        call.nearest_annot_1b = near
        call.delta_to_nearest_annot = delta

        # rewrite kind to exon-based label if available
        if near is not None and donor_kind_by_1b:
            call.kind = donor_kind_by_1b.get(int(near), call.kind)

        prev = donor_by_idx.get(int(call.idx0))
        if (prev is None) or (call.prob > prev.prob):
            donor_by_idx[int(call.idx0)] = call

    donor_calls = sorted(donor_by_idx.values(), key=lambda x: float(x.prob), reverse=True)[:top_k]

    acceptor_by_idx: Dict[int, SiteCall] = {}
    for i in acceptor_candidates:
        i = int(i)
        call = snap_to_canonical_motif(
            seq_ref,
            acceptor_probs,
            mapping,
            "acceptor",
            i,
            max_shift=snap_k,
            donor_label_mode=donor_label_mode,
        )
        near, delta = nearest_site(call.genomic_1b, acceptor_sites_1b)
        call.nearest_annot_1b = near
        call.delta_to_nearest_annot = delta

        if near is not None and acceptor_kind_by_1b:
            call.kind = acceptor_kind_by_1b.get(int(near), call.kind)

        prev = acceptor_by_idx.get(int(call.idx0))
        if (prev is None) or (call.prob > prev.prob):
            acceptor_by_idx[int(call.idx0)] = call

    acceptor_calls = sorted(acceptor_by_idx.values(), key=lambda x: float(x.prob), reverse=True)[:top_k]

    return {"donor": donor_calls, "acceptor": acceptor_calls}


def calls_at_annotated_sites(
    seq_ref: str,
    prob_ref: np.ndarray,
    mapping: WindowMapping,
    donor_sites_1b: List[int],
    acceptor_sites_1b: List[int],
    *,
    donor_kind_by_1b: Optional[Dict[int, str]] = None,
    acceptor_kind_by_1b: Optional[Dict[int, str]] = None,
    donor_label_mode: str = "exon_end",
    snap_k: int = 5,
    donor_channel: int = 2,
    acceptor_channel: int = 1,
) -> Dict[str, List[SiteCall]]:
    """Evaluate model probabilities *at* annotated splice sites inside the current window.

    Why this exists:
      - Top-k scanning across the whole window is useful to find novel sites,
        but acceptor (AG) motifs are very frequent, so top-k can include many
        false positives.
      - For mission-style validation, it's often more meaningful to look at the
        predicted probability at each *known* junction (internal exon starts/ends).

    Conventions (must match your preprocessing):
      - acceptor site = exon START (label placed on the first exon base)
      - donor site    = exon END   (label placed on the last exon base)
      - transcript start/end junctions are already excluded in donor_sites_1b / acceptor_sites_1b.

    We optionally snap each annotated site within ±snap_k to the best canonical motif
    (AG for acceptor, GT/GC for donor), choosing the index with max probability.
    """
    if prob_ref.ndim != 2:
        raise ValueError(f"prob_ref must be 2D (3,L), got {prob_ref.shape}")
    if prob_ref.shape[0] != 3 and prob_ref.shape[1] == 3:
        # tolerate (L,3)
        prob_ref = prob_ref.T
    if prob_ref.shape[0] != 3:
        raise ValueError(f"prob_ref must be (3,L), got {prob_ref.shape}")

    L = len(seq_ref)
    if prob_ref.shape[1] != L:
        raise ValueError(f"prob_ref length mismatch: seq={L} vs prob={prob_ref.shape[1]}")
    if not (0 <= donor_channel < 3 and 0 <= acceptor_channel < 3):
        raise ValueError("donor_channel/acceptor_channel must be in {0,1,2}")

    donor_probs = prob_ref[donor_channel]
    acceptor_probs = prob_ref[acceptor_channel]

    donor_calls: List[SiteCall] = []
    for site_1b in donor_sites_1b:
        idx0 = int(mapping.genomic_1b_to_idx(int(site_1b)))
        if not (0 <= idx0 < L):
            continue
        call = snap_to_canonical_motif(
            seq_ref,
            donor_probs,
            mapping,
            "donor",
            idx0,
            max_shift=snap_k,
            donor_label_mode=donor_label_mode,
        )
        call.nearest_annot_1b = int(site_1b)
        call.delta_to_nearest_annot = int(call.genomic_1b) - int(site_1b)
        if donor_kind_by_1b:
            call.kind = donor_kind_by_1b.get(int(site_1b), call.kind)
        donor_calls.append(call)

    acceptor_calls: List[SiteCall] = []
    for site_1b in acceptor_sites_1b:
        idx0 = int(mapping.genomic_1b_to_idx(int(site_1b)))
        if not (0 <= idx0 < L):
            continue
        call = snap_to_canonical_motif(
            seq_ref,
            acceptor_probs,
            mapping,
            "acceptor",
            idx0,
            max_shift=snap_k,
            donor_label_mode=donor_label_mode,
        )
        call.nearest_annot_1b = int(site_1b)
        call.delta_to_nearest_annot = int(call.genomic_1b) - int(site_1b)
        if acceptor_kind_by_1b:
            call.kind = acceptor_kind_by_1b.get(int(site_1b), call.kind)
        acceptor_calls.append(call)

    return {"donor": donor_calls, "acceptor": acceptor_calls}
