from __future__ import annotations

import numpy as np

def one_hot_encode(seq: str) -> np.ndarray:
    """One-hot encode DNA to shape (4, L) float32 with channels A,C,G,T.

    Unknown / N -> all zeros.
    """
    m = {"A": 0, "C": 1, "G": 2, "T": 3}
    L = len(seq)
    X = np.zeros((L, 4), dtype=np.float32)
    for i, ch in enumerate(seq.upper()):
        j = m.get(ch)
        if j is not None:
            X[i, j] = 1.0
    return X.T  # (4, L)
