from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import torch
import torch.nn.functional as F
from tqdm import tqdm

from ..mission6.encoding import one_hot_encode
from .constants import core_slice


@dataclass
class InferenceConfig:
    batch_size: int = 4
    device: Optional[str] = None  # 'cpu' / 'cuda' / 'mps'

    def torch_device(self) -> torch.device:
        if self.device:
            return torch.device(self.device)
        if torch.cuda.is_available():
            return torch.device("cuda")
        # MPS is useful on Apple Silicon for quick checks
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")


def encode_sequences(seqs: List[str]) -> np.ndarray:
    """Encode list of sequences to (N,4,L) float32 numpy."""
    X_list = [one_hot_encode(s) for s in seqs]
    return np.stack(X_list, axis=0)


def predict_probs_center_crop(
    model: torch.nn.Module,
    X: np.ndarray,
    *,
    in_length: int,
    out_length: int,
    cfg: InferenceConfig = InferenceConfig(),
) -> np.ndarray:
    """Run model on (N,4,in_length) and return probs (N,3,out_length).

    We run the model on full input length, then center-crop the logits to out_length
    (SpliceAI-10k style: 15000 -> 5000).
    """
    if X.ndim != 3:
        raise ValueError(f"X must be (N,4,L), got {X.shape}")
    if X.shape[2] != int(in_length):
        raise ValueError(f"Expected X length {in_length}, got {X.shape[2]}")
    sl = core_slice(in_length, out_length)

    device = cfg.torch_device()
    model = model.to(device)

    N = X.shape[0]
    out_list: List[np.ndarray] = []

    with torch.no_grad():
        for i in tqdm(range(0, N, cfg.batch_size), desc="inference", leave=False):
            xb = torch.from_numpy(X[i : i + cfg.batch_size]).to(device)
            logits = model(xb)  # (B,3,in_length)
            if logits.ndim != 3 or logits.shape[1] != 3:
                raise ValueError(f"Unexpected logits shape: {tuple(logits.shape)}")
            logits = logits[:, :, sl]  # (B,3,out_length)
            probs = F.softmax(logits, dim=1).detach().cpu().numpy()
            out_list.append(probs)

    return np.concatenate(out_list, axis=0)
