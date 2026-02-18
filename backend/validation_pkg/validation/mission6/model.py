from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

import torch
import torch.nn as nn


class ResBlock(nn.Module):
    def __init__(self, c_in: int, c_out: int, kernel_size: int = 1, padding: str = "same", dilation: int = 1):
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
    """Mission6 inference model (no center-crop; works with any length)."""

    def __init__(self):
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


def _extract_state_dict(obj: Any) -> Dict[str, torch.Tensor]:
    """Handle various checkpoint formats."""
    if isinstance(obj, dict):
        # common patterns
        if "state_dict" in obj and isinstance(obj["state_dict"], dict):
            return obj["state_dict"]
        if "model_state_dict" in obj and isinstance(obj["model_state_dict"], dict):
            return obj["model_state_dict"]
        # might already be a state dict
        if all(isinstance(k, str) for k in obj.keys()):
            return obj  # type: ignore[return-value]
    raise ValueError("Unsupported checkpoint format; expected a state_dict-like dict.")


def load_model(ckpt_path: str, device: Optional[torch.device] = None) -> SpliceAI:
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SpliceAI().to(device)
    ckpt = torch.load(ckpt_path, map_location=device)
    state = _extract_state_dict(ckpt)
    model.load_state_dict(state, strict=True)
    model.eval()
    return model
