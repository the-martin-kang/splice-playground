from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..mission6.backend_client import BackendClient
from ..mission6.model import load_model

from .constants import core_slice
from .inference import InferenceConfig, encode_sequences, predict_probs_center_crop
from .canonical_eval_backend import canonical_sites_from_exons


def _ensure_matplotlib() -> None:
    try:
        import matplotlib  # noqa: F401
    except Exception as e:
        raise SystemExit("matplotlib is required for visualization. Install with: uv add matplotlib") from e


def _safe_name(s: str) -> str:
    return "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in str(s)])


def _is_404(e: Exception) -> bool:
    s = str(e)
    return "status=404" in s or " 404 " in s or "404 Not Found" in s


def main() -> None:
    _ensure_matplotlib()
    import matplotlib.pyplot as plt

    ap = argparse.ArgumentParser(
        description="Visualize SNV-centered ref vs alt splice probabilities (gene0 axis) with canonical splice-site markers from Supabase." 
    )
    ap.add_argument("--backend-url", required=True)
    ap.add_argument("--model", required=True)

    ap.add_argument("--disease-id", default=None, help="If set, plot only this disease_id")
    ap.add_argument("--out-dir", default="plots_spliceai10k_gene0")

    ap.add_argument("--window-size", type=int, default=15000)
    ap.add_argument("--out-len", type=int, default=5000)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--device", default=None)

    ap.add_argument("--dpi", type=int, default=160)
    ap.add_argument("--label", action="store_true", help="Annotate canonical site kinds on the plot")

    args = ap.parse_args()

    bc = BackendClient(args.backend_url)
    model = load_model(args.model)
    cfg = InferenceConfig(batch_size=int(args.batch_size), device=args.device)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # disease list
    if args.disease_id:
        disease_ids = [str(args.disease_id)]
        disease_meta_by_id: Dict[str, Dict[str, Any]] = {}
    else:
        ds = bc.list_diseases()
        disease_ids = [str(d["disease_id"]) for d in ds if d.get("disease_id")]
        disease_meta_by_id = {str(d.get("disease_id")): d for d in ds if d.get("disease_id")}

    html = [
        "<html><head><meta charset='utf-8'><title>SpliceAI10k SNV plots</title></head><body>",
        "<h1>SpliceAI10k SNV-centered plots (gene0 axis)</h1>",
        f"<p>window_size={args.window_size}, out_len={args.out_len}</p>",
    ]

    for did in disease_ids:
        # 1) fetch window (ref/alt strings)
        w = bc.get_window_4000(did, window_size=int(args.window_size), strict_ref_check=False)
        ref_seq = w["ref_seq_4000"]
        alt_seq = w["alt_seq_4000"]
        window_start = int(w["window_start_gene0"])
        pos_gene0 = int(w["pos_gene0"])
        gene_id = str(w.get("gene_id") or "")

        # 2) fetch exon regions (to derive canonical splice sites)
        step2 = bc.get_step2_payload(did, include_sequence=False)
        gene = step2.get("gene") or {}
        exon_count = int(gene.get("exon_count"))

        exons: List[Dict[str, Any]] = []
        for n in range(1, exon_count + 1):
            reg = bc.get_region(did, "exon", n, include_sequence=False)
            exons.append(reg["region"] if "region" in reg else reg)

        canonical_sites = canonical_sites_from_exons(exons, exon_count=exon_count)

        # 3) run inference (core only)
        X = encode_sequences([ref_seq, alt_seq])
        prob = predict_probs_center_crop(
            model,
            X,
            in_length=int(args.window_size),
            out_length=int(args.out_len),
            cfg=cfg,
        )
        prob_ref = prob[0]  # (3,out_len)
        prob_alt = prob[1]

        sl = core_slice(int(args.window_size), int(args.out_len))
        core_start = int(sl.start or 0)
        core_gene0_start = window_start + core_start
        x = core_gene0_start + np.arange(int(args.out_len), dtype=int)

        # canonical markers inside the core view
        can_acc = [s for s in canonical_sites if s.site_type == "acceptor" and core_gene0_start <= s.pos_gene0 < core_gene0_start + int(args.out_len)]
        can_don = [s for s in canonical_sites if s.site_type == "donor" and core_gene0_start <= s.pos_gene0 < core_gene0_start + int(args.out_len)]

        # 4) plot
        fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True)

        axes[0].plot(x, prob_ref[1], label="ref_acceptor")
        axes[0].plot(x, prob_alt[1], label="alt_acceptor")
        axes[0].set_ylabel("P(acceptor)")
        axes[0].legend(loc="upper right")

        axes[1].plot(x, prob_ref[2], label="ref_donor")
        axes[1].plot(x, prob_alt[2], label="alt_donor")
        axes[1].set_ylabel("P(donor)")
        axes[1].set_xlabel("gene0 position")
        axes[1].legend(loc="upper right")

        # variant marker
        for ax in axes:
            ax.axvline(pos_gene0, linestyle="--", linewidth=1)

        # canonical markers
        for s in can_acc:
            axes[0].axvline(int(s.pos_gene0), linewidth=0.8, alpha=0.3)
            if args.label:
                axes[0].text(int(s.pos_gene0), 1.02, s.kind, rotation=90, fontsize=8, va="bottom")
        for s in can_don:
            axes[1].axvline(int(s.pos_gene0), linewidth=0.8, alpha=0.3)
            if args.label:
                axes[1].text(int(s.pos_gene0), 1.02, s.kind, rotation=90, fontsize=8, va="bottom")

        disease_name = disease_meta_by_id.get(did, {}).get("disease_name") or (step2.get("disease") or {}).get("disease_name")
        title = f"{gene_id} | {did}"
        if disease_name:
            title += f" | {disease_name}"
        fig.suptitle(title)

        fname = f"{_safe_name(gene_id or did)}_{_safe_name(did)}.png"
        out_path = out_dir / fname
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(out_path, dpi=int(args.dpi))
        plt.close(fig)

        html.append(f"<h2>{title}</h2><img src='{fname}' style='max-width: 100%;' />")

    html.append("</body></html>")
    (out_dir / "index.html").write_text("\n".join(html), encoding="utf-8")

    print(f"[OK] wrote plots -> {out_dir}")
    print(f"[OK] open: {out_dir / 'index.html'}")


if __name__ == "__main__":
    main()
