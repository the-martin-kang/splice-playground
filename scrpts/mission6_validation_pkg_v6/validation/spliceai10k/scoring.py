from __future__ import annotations

from typing import Optional

import numpy as np


def calculate_variant_score(
    prob_ref: np.ndarray,
    prob_alt: np.ndarray,
    *,
    score_slice: Optional[slice] = None,
) -> np.ndarray:
    """Mission6-style custom variant score (generalized).

    prob_* shape: (N, 3, L)
      - diff = |alt - ref|
      - weight splicing channels (1,2) by (1 - ref_prob) to emphasize neither->(donor/acceptor)
      - sum over channels and positions

    For SpliceAI-10k validation, we typically use the full output core (L=5000).
    """
    if prob_ref.shape != prob_alt.shape:
        raise ValueError(f"Shape mismatch: ref={prob_ref.shape}, alt={prob_alt.shape}")
    if prob_ref.ndim != 3 or prob_ref.shape[1] != 3:
        raise ValueError(f"Expected (N,3,L), got {prob_ref.shape}")

    sl = score_slice if score_slice is not None else slice(None)

    diff = np.abs(prob_alt[:, :, sl] - prob_ref[:, :, sl])
    weight = 1.0 - prob_ref[:, 1:3, sl]
    diff[:, 1:3, :] *= weight
    return diff.sum(axis=(1, 2))
