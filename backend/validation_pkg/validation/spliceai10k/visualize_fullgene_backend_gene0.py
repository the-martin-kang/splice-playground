"""Visualize SpliceAI10k predictions across the *entire* gene (gene0 axis).

This expands the previous mission6-style window (core_len=5000) plot to cover
gene start -> gene end.

Design goals
  - Use *DB regions* (via backend region endpoints) to assemble the full gene0
    sequence. This validates what STEP3 backend will actually consume.
  - Run the model in a memory-conscious way:
      * default: full-gene single forward pass with N padding on both sides
        (works well for ~100kb genes on 48GB RAM)
      * optional: chunked stitching (safer for very long genes)

Run (example)
  uv run python -m validation_pkg.validation.spliceai10k.visualize_fullgene_backend_gene0 \
    --backend-url https://YOUR.apprunner.com \
    --model /path/to/spliceai_window=10000.pt \
    --window-size 15000 \
    --out-len 5000 \
    --out-dir validation_pkg/report/plots_fullgene_spliceai10k
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from ..mission6.backend_client import BackendClient
from ..mission6.model import load_model
from .inference import InferenceConfig, encode_sequences, predict_probs_center_crop


def _ensure_matplotlib():
    try:
        import matplotlib.pyplot as plt  # type: ignore
        from matplotlib.patches import Rectangle  # type: ignore

        return plt, Rectangle
    except Exception as e:  # pragma: no cover
        raise SystemExit(
            "matplotlib is required for visualization. Install it with: pip install matplotlib"
        ) from e


_COMP = {"A": "T", "T": "A", "C": "G", "G": "C", "N": "N"}


def _complement_base(b: str) -> str:
    return _COMP.get(b.upper(), "N")


def _apply_snv_on_gene0_seq(
    gene_seq: str, *, pos_gene0: int, ref: str, alt: str, strand: str
) -> Tuple[str, Dict[str, object]]:
    """Apply SNV to gene0 sequence.

    Notes
    - DB stores SNV ref/alt in "positive strand" convention (per your decision).
    - Our gene0 sequence is in transcript order.
      For (-) strand genes, the base in gene0 is the *complement* of the positive
      strand base. Therefore, when strand == '-', we complement ref/alt if needed.
    """

    if not (0 <= pos_gene0 < len(gene_seq)):
        raise ValueError(f"SNV pos_gene0 out of range: {pos_gene0} (len={len(gene_seq)})")

    base = gene_seq[pos_gene0].upper()
    ref_u = ref.upper()
    alt_u = alt.upper()
    used_ref = ref_u
    used_alt = alt_u
    mode = "direct"

    if base == ref_u:
        new_base = alt_u
        ok = True
    else:
        # Try complement (common for (-) strand if ref/alt stored as + strand).
        cref = _complement_base(ref_u)
        calt = _complement_base(alt_u)
        if base == cref:
            new_base = calt
            used_ref = cref
            used_alt = calt
            mode = "complement"
            ok = True
        else:
            # As a last resort, still apply alt (or its complement for '-' strand)
            # but mark as mismatch.
            if strand == "-":
                new_base = _complement_base(alt_u)
                used_ref = cref
                used_alt = _complement_base(alt_u)
                mode = "forced_complement_alt"
            else:
                new_base = alt_u
                mode = "forced_alt"
            ok = False

    out = list(gene_seq)
    out[pos_gene0] = new_base
    info = {
        "ok": ok,
        "mode": mode,
        "pos_gene0": pos_gene0,
        "base_before": base,
        "ref_input": ref_u,
        "alt_input": alt_u,
        "ref_used": used_ref,
        "alt_used": used_alt,
        "base_after": new_base,
    }
    return "".join(out), info


def _fetch_all_regions_with_sequence(bc: BackendClient, disease_id: str, exon_count: int) -> List[Dict[str, object]]:
    regions: List[Dict[str, object]] = []

    for exon_num in range(1, exon_count + 1):
        payload = bc.get_region(disease_id, "exon", exon_num, include_sequence=True)
        region = payload.get("region") or {}
        if not region:
            raise RuntimeError(f"Missing exon {exon_num} for disease_id={disease_id}")
        region = dict(region)
        region["region_type"] = "exon"
        region["region_number"] = exon_num
        regions.append(region)

    for intron_num in range(1, exon_count):
        payload = bc.get_region(disease_id, "intron", intron_num, include_sequence=True)
        region = payload.get("region") or {}
        if not region:
            raise RuntimeError(f"Missing intron {intron_num} for disease_id={disease_id}")
        region = dict(region)
        region["region_type"] = "intron"
        region["region_number"] = intron_num
        regions.append(region)

    return regions


def _assemble_gene0_sequence(gene_length: int, regions: List[Dict[str, object]]) -> str:
    seq = ["N"] * gene_length

    for r in regions:
        s = (r.get("sequence") or "").upper()
        if not s:
            continue
        start = int(r["gene_start_idx"])  # 0-based inclusive
        end = int(r["gene_end_idx"])  # 0-based inclusive
        expected = end - start + 1
        if expected != len(s):
            # Some data sources use end-exclusive. Try to recover.
            if end - start == len(s):
                end = start + len(s) - 1
                expected = end - start + 1
            else:
                raise ValueError(
                    f"Region length mismatch: {r.get('region_id')} {r.get('region_type')}#{r.get('region_number')} "
                    f"start={start} end={end} expected={expected} seq_len={len(s)}"
                )
        if start < 0 or end >= gene_length:
            raise ValueError(
                f"Region out of bounds: start={start} end={end} gene_length={gene_length} (disease gene0 space)"
            )
        seq[start : end + 1] = list(s)

    return "".join(seq)


def _predict_full_gene_probs(
    model,
    *,
    gene_seq: str,
    pad_each: int,
    cfg: InferenceConfig,
    chunked: bool,
    chunk_stride: int,
    chunk_window: int,
    chunk_out: int,
) -> np.ndarray:
    """Return probs (3, gene_length) in gene0 order."""

    gene_len = len(gene_seq)

    if not chunked:
        seq_in = ("N" * pad_each) + gene_seq + ("N" * pad_each)
        X = encode_sequences([seq_in])
        prob = predict_probs_center_crop(model, X, in_length=len(seq_in), out_length=gene_len, cfg=cfg)
        return prob[0]

    # Chunked stitching: run windows of `chunk_window` and stitch central `chunk_out`.
    # This is safer for very long genes, at the cost of more forward passes.
    if chunk_window <= chunk_out:
        raise ValueError("chunk_window must be larger than chunk_out")
    flank = (chunk_window - chunk_out) // 2
    if chunk_window - chunk_out != 2 * flank:
        raise ValueError("chunk_window - chunk_out must be even")

    # pad for context
    ext = ("N" * flank) + gene_seq + ("N" * flank)
    L = gene_len
    sum_prob = np.zeros((3, L), dtype=np.float32)
    cnt = np.zeros((L,), dtype=np.float32)

    max_start = max(L - chunk_out, 0)
    starts = list(range(0, max_start + 1, chunk_stride))
    if starts and starts[-1] != max_start:
        starts.append(max_start)
    if not starts:
        starts = [0]

    for s in starts:
        win = ext[s : s + chunk_window]
        X = encode_sequences([win])
        prob = predict_probs_center_crop(model, X, in_length=len(win), out_length=chunk_out, cfg=cfg)[0]  # (3, chunk_out)
        e = min(s + chunk_out, L)
        used = e - s
        sum_prob[:, s:e] += prob[:, :used]
        cnt[s:e] += 1.0

    cnt[cnt == 0] = 1.0
    return sum_prob / cnt


def _plot_full_gene_gene0(
    *,
    out_path: Path,
    gene_id: str,
    disease_id: str,
    disease_name: str,
    strand: str,
    regions: List[Dict[str, object]],
    prob_ref: np.ndarray,
    prob_alt: Optional[np.ndarray],
    snv_pos_gene0: int,
    title_extra: str = "",
):
    plt, Rectangle = _ensure_matplotlib()

    gene_len = prob_ref.shape[1]
    x = np.arange(gene_len)

    exons = [r for r in regions if r.get("region_type") == "exon"]
    exons.sort(key=lambda r: int(r.get("region_number") or 0))
    exon_count = len(exons)

    fig = plt.figure(figsize=(20, 10))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.0, 2.0, 2.0], hspace=0.35)
    ax_track = fig.add_subplot(gs[0, 0])
    ax_acc = fig.add_subplot(gs[1, 0], sharex=ax_track)
    ax_don = fig.add_subplot(gs[2, 0], sharex=ax_track)

    # --- Exon track (gene0 axis) ---
    ax_track.hlines(0.5, 0, gene_len - 1, linewidth=1.0)
    for ex in exons:
        s = int(ex["gene_start_idx"])
        e = int(ex["gene_end_idx"])
        width = e - s + 1
        ax_track.add_patch(Rectangle((s, 0.25), width, 0.5, linewidth=0.8, edgecolor="0.3", facecolor="0.75"))
        if exon_count <= 60:
            ax_track.text(
                s + width / 2.0,
                0.5,
                str(ex.get("region_number")),
                ha="center",
                va="center",
                fontsize=7,
                color="0.1",
            )

    ax_track.set_ylim(0, 1)
    ax_track.set_yticks([])
    ax_track.set_ylabel("Exons")

    # --- Probability curves ---
    ax_acc.plot(x, prob_ref[1], label="Ref")
    if prob_alt is not None:
        ax_acc.plot(x, prob_alt[1], label="Alt", alpha=0.75)
    ax_acc.axvline(snv_pos_gene0, linestyle="--", linewidth=1.0)
    ax_acc.set_ylabel("P(acceptor)")
    ax_acc.set_ylim(0, 1.0)
    ax_acc.legend(loc="upper right")

    ax_don.plot(x, prob_ref[2], label="Ref")
    if prob_alt is not None:
        ax_don.plot(x, prob_alt[2], label="Alt", alpha=0.75)
    ax_don.axvline(snv_pos_gene0, linestyle="--", linewidth=1.0)
    ax_don.set_ylabel("P(donor)")
    ax_don.set_ylim(0, 1.0)
    ax_don.legend(loc="upper right")
    ax_don.set_xlabel("Gene-local coordinate (gene0, 0-based)")

    title = f"{disease_id} | {gene_id} ({strand})"
    if title_extra:
        title = f"{title} | {title_extra}"
    fig.suptitle(title, y=0.995, fontsize=14)
    ax_acc.set_title(disease_name, loc="left", fontsize=12, pad=10)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description="Visualize full-gene SpliceAI10k probabilities (gene0 axis)")
    p.add_argument("--backend-url", default="http://localhost:8000", help="Backend base URL")
    p.add_argument("--model", type=str, required=True, help="Path to trained model .pt")
    p.add_argument("--out-dir", type=str, required=True, help="Output directory for PNG plots")

    # Default: run for all diseases returned by GET /api/diseases.
    # You can optionally restrict to specific disease_id(s).
    p.add_argument(
        "--disease-id",
        action="append",
        default=[],
        help="Restrict to a specific disease_id. Can be provided multiple times.",
    )

    p.add_argument(
        "--window-size",
        type=int,
        default=15000,
        help="Input length used by the model in training/inference (for context size derivation)",
    )
    p.add_argument(
        "--out-len",
        type=int,
        default=5000,
        help="Central output length used in training (for context size derivation)",
    )
    p.add_argument("--device", type=str, default="cpu", help="cpu|mps|cuda")

    p.add_argument(
        "--chunked",
        action="store_true",
        help="Use chunked stitching instead of single full-gene forward pass (safer for huge genes)",
    )
    p.add_argument(
        "--chunk-window",
        type=int,
        default=15000,
        help="Chunk input length (when --chunked). Typically same as --window-size.",
    )
    p.add_argument(
        "--chunk-out",
        type=int,
        default=5000,
        help="Chunk output length (when --chunked). Typically same as --out-len.",
    )
    p.add_argument(
        "--chunk-stride",
        type=int,
        default=5000,
        help="Stride in gene0 positions between chunks (when --chunked). Default=chunk_out.",
    )
    p.add_argument("--max-genes", type=int, default=0, help="If >0, limit number of diseases")

    args = p.parse_args()

    out_dir = Path(args.out_dir)

    if args.window_size <= args.out_len:
        raise SystemExit("--window-size must be larger than --out-len")
    pad_each = (args.window_size - args.out_len) // 2
    if (args.window_size - args.out_len) != 2 * pad_each:
        raise SystemExit("--window-size - --out-len must be even")

    bc = BackendClient(args.backend_url)

    # Default worklist: backend diseases (keeps validation in sync with DB).
    if args.disease_id:
        disease_ids = [str(x) for x in args.disease_id]
    else:
        diseases = bc.list_diseases()
        disease_ids = [str(d.get("disease_id")) for d in diseases if d.get("disease_id")]
        disease_ids.sort()  # stable order for regression

    if args.max_genes and args.max_genes > 0:
        disease_ids = disease_ids[: args.max_genes]

    if not disease_ids:
        raise SystemExit("No diseases found. Check --backend-url and that /api/diseases is reachable.")
    """
    PATH = "/Users/martin/Git/splice-playground/backend/app/ai_models/spliceai_window=10000.pt"
    state_dict = torch.load(PATH, map_location="cpu")
    model = SpliceAI()
    model.load_state_dict(state_dict)

    model.to(device)
    print(device)
    """

    model = load_model(args.model)
    cfg = InferenceConfig(device=args.device)

    # Warm-up: move to device once.
    model = model.to(cfg.device)
    model.eval()

    for did in disease_ids:
        payload = bc.get_step2_payload(did, include_sequence=False)
        disease = payload.get("disease") or {}
        gene = payload.get("gene") or {}
        snv = payload.get("splice_altering_snv") or {}

        gene_id = str(gene.get("gene_id") or disease.get("gene_id") or "")
        disease_name = str(disease.get("disease_name") or "")
        strand = str(gene.get("strand") or "+")
        gene_length = int(gene.get("length") or 0)
        exon_count = int(gene.get("exon_count") or 0)
        if not gene_id or gene_length <= 0 or exon_count <= 0:
            raise RuntimeError(f"Invalid gene metadata for disease_id={did}: {gene}")

        pos_gene0 = int(snv.get("pos_gene0"))
        ref = str(snv.get("ref"))
        alt = str(snv.get("alt"))

        regions = _fetch_all_regions_with_sequence(bc, did, exon_count)
        gene_seq = _assemble_gene0_sequence(gene_length, regions)

        alt_seq, snv_info = _apply_snv_on_gene0_seq(
            gene_seq, pos_gene0=pos_gene0, ref=ref, alt=alt, strand=strand
        )

        prob_ref = _predict_full_gene_probs(
            model,
            gene_seq=gene_seq,
            pad_each=pad_each,
            cfg=cfg,
            chunked=bool(args.chunked),
            chunk_stride=int(args.chunk_stride),
            chunk_window=int(args.chunk_window),
            chunk_out=int(args.chunk_out),
        )
        prob_alt = _predict_full_gene_probs(
            model,
            gene_seq=alt_seq,
            pad_each=pad_each,
            cfg=cfg,
            chunked=bool(args.chunked),
            chunk_stride=int(args.chunk_stride),
            chunk_window=int(args.chunk_window),
            chunk_out=int(args.chunk_out),
        )

        out_path = out_dir / f"{gene_id}_{did}_fullgene_gene0_ws{args.window_size}_out{args.out_len}.png"
        title_extra = "" if snv_info.get("ok") else f"SNV_REF_MISMATCH(mode={snv_info.get('mode')})"

        _plot_full_gene_gene0(
            out_path=out_path,
            gene_id=gene_id,
            disease_id=did,
            disease_name=disease_name,
            strand=strand,
            regions=regions,
            prob_ref=prob_ref,
            prob_alt=prob_alt,
            snv_pos_gene0=pos_gene0,
            title_extra=title_extra,
        )

        print(f"[OK] wrote plot -> {out_path}")


if __name__ == "__main__":
    main()
