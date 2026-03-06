from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F


# ---- encoding ----

def one_hot_encode(seq: str) -> np.ndarray:
    """One-hot encode DNA to shape (4, L) float32 with channels A,C,G,T.

    Unknown / N -> all zeros.
    """
    m = {"A": 0, "C": 1, "G": 2, "T": 3}
    L = len(seq)
    X = np.zeros((L, 4), dtype=np.float32)
    s = seq.upper()
    for i, ch in enumerate(s):
        j = m.get(ch)
        if j is not None:
            X[i, j] = 1.0
    return X.T  # (4, L)


def core_slice(in_length: int, out_length: int) -> slice:
    """Return slice selecting the centered out_length region from an in_length array."""
    if out_length > in_length:
        raise ValueError(f"out_length({out_length}) must be <= in_length({in_length})")
    start = int((in_length - out_length) // 2)
    end = start + int(out_length)
    return slice(start, end)


@dataclass
class InferenceConfig:
    device: Optional[str] = None  # 'cpu' / 'cuda' / 'mps'

    def torch_device(self) -> torch.device:
        if self.device:
            return torch.device(self.device)
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")


def predict_probs_center_crop(
    model: torch.nn.Module,
    seq: str,
    *,
    in_length: int,
    out_length: int,
    cfg: InferenceConfig = InferenceConfig(),
) -> np.ndarray:
    """Run model on a single sequence and return probs (3, out_length).

    Assumes model output logits are (1,3,in_length).
    We center-crop logits to out_length and softmax along class dim.
    """
    if len(seq) != int(in_length):
        raise ValueError(f"Expected seq length {in_length}, got {len(seq)}")

    sl = core_slice(in_length, out_length)
    device = cfg.torch_device()
    model = model.to(device)

    x = one_hot_encode(seq)  # (4,L)
    xb = torch.from_numpy(x).unsqueeze(0).to(device)  # (1,4,L)

    with torch.no_grad():
        logits = model(xb)  # (1,3,L)
        if logits.ndim != 3 or logits.shape[1] != 3:
            raise ValueError(f"Unexpected logits shape: {tuple(logits.shape)}")
        logits = logits[:, :, sl]  # (1,3,out_len)
        probs = F.softmax(logits, dim=1).detach().cpu().numpy()[0]  # (3,out_len)

    return probs


def safe_float_list(x: np.ndarray) -> list:
    """Convert numpy array to nested python lists of floats (JSON safe)."""
    return x.astype(np.float32).tolist()
