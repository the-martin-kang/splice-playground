from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

import numpy as np

# matplotlib is an optional dependency for the backend project.
# This module is only imported when you run visualization commands.
from matplotlib.ticker import ScalarFormatter
from matplotlib.patches import Rectangle
import matplotlib
import matplotlib.pyplot as plt


def _draw_exon_intron_track(
    ax,
    exon_starts: Sequence[int],
    exon_ends: Sequence[int],
    window_start: int,
    window_end: int,
    strand: str,
) -> None:
    """Draw an IGV-style exon/intron cartoon in genomic coordinates.

    exon_starts, exon_ends: 1-based genomic positions (inclusive)
    window_start, window_end: genomic bounds shown on x-axis (1-based, inclusive)
    strand: '+' or '-'
    """
    starts = np.asarray(list(exon_starts), dtype=int)
    ends = np.asarray(list(exon_ends), dtype=int)
    if len(starts) == 0 or len(ends) == 0:
        ax.set_ylim(-0.6, 0.6)
        ax.set_yticks([])
        ax.set_xlim(window_start, window_end)
        ax.set_ylabel("Exons")
        return

    order = np.argsort(starts)
    starts = starts[order]
    ends = ends[order]

    # collect exons overlapping the window, clipped
    for s, e in zip(starts, ends):
        if e < window_start or s > window_end:
            continue
        s_clip = max(int(s), int(window_start))
        e_clip = min(int(e), int(window_end))
        if e_clip > s_clip:
            ax.add_patch(
                Rectangle(
                    (s_clip, -0.5),
                    e_clip - s_clip,
                    1.0,
                    edgecolor="black",
                    facecolor="0.7",
                    linewidth=0.8,
                )
            )

    # introns between consecutive exons (full gene), clipped
    y_intr = 0.0
    direction = 1 if strand == "+" else -1

    for (s1, e1), (s2, e2) in zip(zip(starts, ends), zip(starts[1:], ends[1:])):
        intron_start = int(e1) + 1
        intron_end = int(s2) - 1
        if intron_end <= intron_start:
            continue

        draw_start = max(intron_start, window_start)
        draw_end = min(intron_end, window_end)
        if draw_end <= draw_start:
            continue

        ax.plot([draw_start, draw_end], [y_intr, y_intr], linewidth=1.0, color="k")

        intron_len = draw_end - draw_start
        if intron_len <= 0:
            continue

        n_arrows = max(1, min(3, int(intron_len // 500) + 1))
        xs = np.linspace(
            draw_start + intron_len * 0.2,
            draw_end - intron_len * 0.1,
            n_arrows,
        )
        dx = direction * min(intron_len * 0.2, 200)
        for x_mid in xs:
            ax.annotate(
                "",
                xy=(x_mid + dx * 0.5, y_intr),
                xytext=(x_mid - dx * 0.5, y_intr),
                arrowprops=dict(arrowstyle="->", linewidth=1.0, color="k"),
            )

    ax.set_ylim(-0.6, 0.6)
    ax.set_yticks([])
    ax.set_ylabel("Exons")
    ax.set_xlim(window_start, window_end)


def plot_splicevar_example(
    prob_ref_one: np.ndarray,
    prob_alt_one: np.ndarray,
    *,
    gene: str,
    chrom: str,
    pos_1b: int,
    strand: str,
    ref: str,
    alt: str,
    variant_score: float,
    exon_starts: Optional[Sequence[int]] = None,
    exon_ends: Optional[Sequence[int]] = None,
    zoom: float = 1.0,
    shift: int = 0,
    pad_base: int = 1000,
    title_prefix: str = "",
    subtitle: Optional[str] = None,
):
    """Mission6-style visualization for one variant.

    prob_*_one: (3, L) arrays (softmax probabilities).
    zoom: 1..20. Larger => zoom in (smaller window).
    shift: genomic shift (nt) of window center relative to pos.
    pad_base: base half-window (nt) when zoom=1. Effective pad is pad_base/zoom.
    """
    pr = prob_ref_one
    pa = prob_alt_one
    if pr.shape != pa.shape or pr.ndim != 2 or pr.shape[0] != 3:
        raise ValueError(f"Expected probs (3,L), got ref={pr.shape} alt={pa.shape}")

    L = pr.shape[1]
    center_idx = L // 2  # even -> right-center (e.g. 4000 -> 2000)

    acc_ref = pr[1]
    acc_alt = pa[1]
    don_ref = pr[2]
    don_alt = pa[2]

    # Strand-aware mapping index -> genomic coordinate
    if strand == "+":
        x_full = pos_1b + (np.arange(L) - center_idx)
        acc_ref_full = acc_ref
        acc_alt_full = acc_alt
        don_ref_full = don_ref
        don_alt_full = don_alt
    else:
        x_raw = pos_1b - (np.arange(L) - center_idx)
        x_full = x_raw[::-1]
        acc_ref_full = acc_ref[::-1]
        acc_alt_full = acc_alt[::-1]
        don_ref_full = don_ref[::-1]
        don_alt_full = don_alt[::-1]

    # zoom & shift => choose sub-window
    zoom = float(zoom)
    if zoom <= 0:
        zoom = 1.0
    zoom_inv = 1.0 / zoom
    zoom_inv = max(0.05, min(zoom_inv, 1.0))
    pad_eff = int(pad_base * zoom_inv)

    center_genomic = int(pos_1b) + int(shift)
    window_start = center_genomic - pad_eff
    window_end = center_genomic + pad_eff

    mask = (x_full >= window_start) & (x_full <= window_end)
    if not np.any(mask):
        x = np.array([window_start, window_end])
        acc_ref_plot = np.zeros_like(x, dtype=float)
        acc_alt_plot = np.zeros_like(x, dtype=float)
        don_ref_plot = np.zeros_like(x, dtype=float)
        don_alt_plot = np.zeros_like(x, dtype=float)
    else:
        x = x_full[mask]
        acc_ref_plot = acc_ref_full[mask]
        acc_alt_plot = acc_alt_full[mask]
        don_ref_plot = don_ref_full[mask]
        don_alt_plot = don_alt_full[mask]

    fig, axes = plt.subplots(
        3, 1,
        figsize=(12, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [0.7, 1.0, 1.0]},
    )
    ax_exon, ax_acc, ax_don = axes

    if exon_starts is not None and exon_ends is not None:
        _draw_exon_intron_track(ax_exon, exon_starts, exon_ends, window_start, window_end, strand)
    else:
        ax_exon.set_yticks([])
        ax_exon.set_xlim(window_start, window_end)
        ax_exon.set_ylabel("Exons")

    title = f"{gene} ({strand} strand) – {chrom}:{pos_1b} {ref}>{alt} [score={variant_score:.4f}]"
    if title_prefix:
        title = f"{title_prefix}{title}"
    ax_exon.set_title(title)
    if subtitle:
        ax_exon.text(0.01, -0.9, subtitle, transform=ax_exon.transAxes, fontsize=10)

    color_ref = "royalblue"
    color_alt = "tomato"

    ax_acc.plot(x, acc_ref_plot, label="Ref", color=color_ref, lw=2.0, alpha=0.9)
    ax_acc.plot(x, acc_alt_plot, label="Alt", color=color_alt, lw=2.0, alpha=0.6)
    ax_acc.set_ylabel("P(acceptor)")
    ax_acc.set_ylim(0, 1)
    ax_acc.legend(loc="upper right")

    ax_don.plot(x, don_ref_plot, label="Ref", color=color_ref, lw=2.0, alpha=0.9)
    ax_don.plot(x, don_alt_plot, label="Alt", color=color_alt, lw=2.0, alpha=0.6)
    ax_don.set_ylabel("P(donor)")
    ax_don.set_xlabel(f"Genomic coordinate ({chrom})")
    ax_don.set_ylim(0, 1)
    ax_don.legend(loc="upper right")

    for ax in axes:
        ax.axvline(pos_1b, color="black", linestyle="--", linewidth=1, alpha=0.7)

    # disable scientific notation on x axis
    ax_don.ticklabel_format(axis="x", style="plain")
    fmt = ScalarFormatter(useOffset=False)
    fmt.set_scientific(False)
    for ax in axes:
        ax.xaxis.set_major_formatter(fmt)

    fig.tight_layout()
    return fig


def save_figure(fig, out_path: str, dpi: int = 150) -> None:
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
