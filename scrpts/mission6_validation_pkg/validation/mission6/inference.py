from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from tqdm import tqdm

from .encoding import one_hot_encode


@dataclass
class InferenceConfig:
    batch_size: int = 8
    device: Optional[str] = None  # 'cpu' or 'cuda'

    def torch_device(self) -> torch.device:
        if self.device:
            return torch.device(self.device)
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def predict_probs(model: torch.nn.Module, X: np.ndarray, cfg: InferenceConfig = InferenceConfig()) -> np.ndarray:
    """Run model and return softmax probabilities as numpy array: (N, 3, L)."""
    if X.ndim != 3:
        raise ValueError(f"X must be (N,4,L), got {X.shape}")
    device = cfg.torch_device()
    model = model.to(device)

    N = X.shape[0]
    out_list: List[np.ndarray] = []

    with torch.no_grad():
        for i in tqdm(range(0, N, cfg.batch_size), desc="inference", leave=False):
            xb = torch.from_numpy(X[i : i + cfg.batch_size]).to(device)
            logits = model(xb)
            probs = F.softmax(logits, dim=1).detach().cpu().numpy()
            out_list.append(probs)
    return np.concatenate(out_list, axis=0)


def encode_sequences(seqs: List[str]) -> np.ndarray:
    """Encode list of sequences to (N,4,L)."""
    X_list = [one_hot_encode(s) for s in seqs]
    return np.stack(X_list, axis=0)
