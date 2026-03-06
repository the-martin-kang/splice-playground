from __future__ import annotations

import numpy as np

from .constants import SCORE_CENTER_SLICE


def calculate_variant_score(prob_ref: np.ndarray, prob_alt: np.ndarray) -> np.ndarray:
    """Mission6 custom variant score.

    prob_* shape: (N, 3, L). Uses central slice [1000, 3000).
    - diff = |alt - ref|
    - weight splicing channels (1,2) by (1 - ref_prob) to emphasize neither->(donor/acceptor)
    - sum over channels and positions
    """
    if prob_ref.shape != prob_alt.shape:
        raise ValueError(f"Shape mismatch: ref={prob_ref.shape}, alt={prob_alt.shape}")
    if prob_ref.ndim != 3 or prob_ref.shape[1] != 3:
        raise ValueError(f"Expected (N,3,L), got {prob_ref.shape}")

    diff = np.abs(prob_alt[:, :, SCORE_CENTER_SLICE] - prob_ref[:, :, SCORE_CENTER_SLICE])

    weight = 1.0 - prob_ref[:, 1:3, SCORE_CENTER_SLICE]  # (N,2,2000)
    diff[:, 1:3, :] *= weight

    scores = diff.sum(axis=(1, 2))
    return scores
