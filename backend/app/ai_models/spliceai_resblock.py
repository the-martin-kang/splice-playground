from __future__ import annotations

from typing import Any, Dict, Optional

import torch
import torch.nn as nn


class ResBlock(nn.Module):
    """Residual block used in our SpliceAI-style ResNet.

    This mirrors the lightweight ResBlock you used in your Mission6/validation code:
    - BN -> ReLU -> Conv
    - BN -> ReLU -> Conv
    - residual add
    """

    def __init__(
        self,
        c_in: int,
        c_out: int,
        *,
        kernel_size: int = 1,
        padding: str = "same",
        dilation: int = 1,
    ) -> None:
        super().__init__()
        self.path = nn.Sequential(
            nn.BatchNorm1d(c_in),
            nn.ReLU(inplace=True),
            nn.Conv1d(c_in, c_out, kernel_size=kernel_size, padding=padding, dilation=dilation),
            nn.BatchNorm1d(c_out),
            nn.ReLU(inplace=True),
            nn.Conv1d(c_out, c_out, kernel_size=kernel_size, padding=padding, dilation=dilation),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.path(x) + x


class SpliceAI(nn.Module):
    """SpliceAI-style model that returns per-base logits for the whole input length.

    Output: (B, 3, L) logits for classes [neither, acceptor, donor] at each position.
    """

    def __init__(self) -> None:
        super().__init__()
        self.stem = nn.Conv1d(in_channels=4, out_channels=32, kernel_size=1, dilation=1)
        self.conv = nn.Conv1d(in_channels=32, out_channels=32, kernel_size=1, dilation=1)
        self.final = nn.Conv1d(in_channels=32, out_channels=3, kernel_size=1, dilation=1)

        self.phase1 = nn.Sequential(
            ResBlock(32, 32, kernel_size=11, dilation=1),
            ResBlock(32, 32, kernel_size=11, dilation=1),
            ResBlock(32, 32, kernel_size=11, dilation=1),
            ResBlock(32, 32, kernel_size=11, dilation=1),
        )
        self.phase2 = nn.Sequential(
            ResBlock(32, 32, kernel_size=11, dilation=4),
            ResBlock(32, 32, kernel_size=11, dilation=4),
            ResBlock(32, 32, kernel_size=11, dilation=4),
            ResBlock(32, 32, kernel_size=11, dilation=4),
        )
        self.phase3 = nn.Sequential(
            ResBlock(32, 32, kernel_size=21, dilation=10),
            ResBlock(32, 32, kernel_size=21, dilation=10),
            ResBlock(32, 32, kernel_size=21, dilation=10),
            ResBlock(32, 32, kernel_size=21, dilation=10),
        )
        self.phase4 = nn.Sequential(
            ResBlock(32, 32, kernel_size=41, dilation=25),
            ResBlock(32, 32, kernel_size=41, dilation=25),
            ResBlock(32, 32, kernel_size=41, dilation=25),
            ResBlock(32, 32, kernel_size=41, dilation=25),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.stem(x)
        residual = self.conv(x)
        x = self.phase1(x)
        residual = residual + self.conv(x)
        x = self.phase2(x)
        residual = residual + self.conv(x)
        x = self.phase3(x)
        residual = residual + self.conv(x)
        x = self.phase4(x)
        x = residual + self.conv(x)
        x = self.final(x)
        return x


def _looks_like_state_dict(d: Any) -> bool:
    """Heuristic: a real torch state_dict is a dict[str, Tensor]."""
    if not isinstance(d, dict) or len(d) == 0:
        return False
    for k, v in d.items():
        if not isinstance(k, str):
            return False
        if not torch.is_tensor(v):
            return False
    return True


def _strip_prefix(state: Dict[str, torch.Tensor], prefix: str) -> Dict[str, torch.Tensor]:
    if not any(k.startswith(prefix) for k in state.keys()):
        return state
    return {(k[len(prefix) :] if k.startswith(prefix) else k): v for k, v in state.items()}


def _extract_state_dict(obj: Any) -> Dict[str, torch.Tensor]:
    """Handle various checkpoint formats robustly.

    Supported:
      - state_dict only
      - dict with: state_dict / model_state_dict / model
      - DataParallel: keys prefixed with 'module.'
    """
    if isinstance(obj, dict):
        for key in ("state_dict", "model_state_dict", "model"):
            if key in obj and isinstance(obj[key], dict) and _looks_like_state_dict(obj[key]):
                return obj[key]

        if _looks_like_state_dict(obj):
            return obj

    raise ValueError(
        "Unsupported checkpoint format; expected a torch state_dict or a dict containing one (state_dict/model_state_dict/model)."
    )


def load_model(ckpt_path: str, *, device: Optional[torch.device] = None) -> SpliceAI:
    """Load checkpoint into the SpliceAI ResBlock model."""
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SpliceAI().to(device)
    ckpt = torch.load(ckpt_path, map_location=device)
    state = _extract_state_dict(ckpt)

    # Try strict load; if it fails, strip common prefixes and retry
    try:
        model.load_state_dict(state, strict=True)
    except RuntimeError:
        state2 = _strip_prefix(state, "module.")
        state2 = _strip_prefix(state2, "model.")
        model.load_state_dict(state2, strict=True)

    model.eval()
    return model
