from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..mission6.annotation import RefAnnotation
from ..mission6.backend_client import BackendClient
from ..mission6.model import load_model
from ..mission6.plotting import plot_splicevar_example, save_figure

from .constants import IN_LENGTH_DEFAULT, OUT_LENGTH_DEFAULT
from .inference import InferenceConfig, encode_sequences, predict_probs_center_crop
from .scoring import calculate_variant_score


def _safe_name(s: str) -> str:
    return "".join([c if c.isalnum() or c in ("-", "_", ".") else "_" for c in str(s)])


def _pick_seq(payload: Dict[str, Any], key_candidates: List[str]) -> str:
    for k in key_candidates:
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
    raise KeyError(f"Could not find sequence key in payload. Tried: {key_candidates}. Keys={list(payload.keys())}")


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "SpliceAI-10k: mission6-style visualization for DB disease_id (gene0 coordinate). "
            "Uses backend /window endpoint for ref/alt sequence, and refannotation_with_canonical.tsv for exon track."
        )
    )
    p.add_argument("--backend-url", required=True)
    p.add_argument("--annotation", required=True, help="refannotation_with_canonical.tsv")
    p.add_argument("--model", required=True, help="trained model checkpoint (.pt)")
    p.add_argument("--out-dir", default="plots_backend_spliceai10k")
    p.add_argument("--disease-id", default=None, help="If set, plot only this disease_id")

    p.add_argument("--window-size", type=int, default=IN_LENGTH_DEFAULT, help="input length fed to model (e.g. 15000)")
    p.add_argument("--out-len", type=int, default=OUT_LENGTH_DEFAULT, help="core output length (e.g. 5000)")
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--device", default=None)

    # plot controls (reused from mission6)
    p.add_argument("--zoom", type=float, default=1.0, help="1..20 (larger => zoom in)")
    p.add_argument("--shift", type=int, default=0, help="genomic shift (nt) of view center")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--pad-base", type=int, default=2500, help="half-window when zoom=1 (5000 core => 2500)")

    args = p.parse_args()

    if args.out_len > args.window_size:
        raise SystemExit("--out-len must be <= --window-size")

    bc = BackendClient(args.backend_url)
    ann = RefAnnotation(args.annotation)
    model = load_model(args.model)
    cfg = InferenceConfig(batch_size=int(args.batch_size), device=args.device)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # pick diseases
    if args.disease_id:
        disease_ids = [str(args.disease_id)]
    else:
        ds = bc.list_diseases()
        disease_ids = [str(d["disease_id"]) for d in ds if d.get("disease_id")]

    for did in disease_ids:
        step2 = bc.get_step2_payload(did, include_sequence=False)
        gene = step2.get("gene") or {}
        disease = step2.get("disease") or {}
        snv = step2.get("splice_altering_snv") or {}

        gene_id = str(gene.get("gene_id") or disease.get("gene_id") or "")
        if not gene_id:
            raise ValueError(f"Missing gene_id for disease_id={did}")

        # annotation row (for exon track + genomic mapping)
        row = ann.get_gene_row(gene_id)
        strand = str(row["STRAND"])
        tx_start_1b = int(row["TX_START"])
        tx_end_1b = int(row["TX_END"])

        # SNV center in gene0
        pos_gene0 = int(snv.get("pos_gene0"))
        if strand == "+":
            pos_1b = tx_start_1b + pos_gene0
        else:
            pos_1b = tx_end_1b - pos_gene0

        # fetch backend window (gene0-centered around SNV)
        payload = bc.get_window_4000(did, window_size=int(args.window_size), strict_ref_check=False)

        ref_seq = _pick_seq(payload, ["ref_seq", "ref_seq_4000", "ref_seq_window", "ref_seq_window_size"])
        alt_seq = _pick_seq(payload, ["alt_seq", "alt_seq_4000", "alt_seq_window", "alt_seq_window_size"])

        if len(ref_seq) != int(args.window_size) or len(alt_seq) != int(args.window_size):
            raise ValueError(
                f"Backend window size mismatch for {did}: "
                f"len(ref)={len(ref_seq)} len(alt)={len(alt_seq)} expected={args.window_size}"
            )

        X = encode_sequences([ref_seq.upper(), alt_seq.upper()])
        prob = predict_probs_center_crop(
            model,
            X,
            in_length=int(args.window_size),
            out_length=int(args.out_len),
            cfg=cfg,
        )  # (2,3,L)

        # For scoring we keep a batch dimension (N=1).
        prob_ref = prob[0:1]  # (1,3,L)
        prob_alt = prob[1:2]  # (1,3,L)

        score = float(calculate_variant_score(prob_ref, prob_alt)[0])

        # For mission6-style plotting we pass (3,L) arrays.
        prob_ref_one = prob[0]
        prob_alt_one = prob[1]

        fig = plot_splicevar_example(
            prob_ref_one,
            prob_alt_one,
            gene=gene_id,
            chrom=str(row["CHROM"]),
            pos_1b=int(pos_1b),
            strand=strand,
            ref=str(snv.get("ref") or "?"),
            alt=str(snv.get("alt") or "?"),
            variant_score=score,
            exon_starts=row["EXON_START"],
            exon_ends=row["EXON_END"],
            zoom=float(args.zoom),
            shift=int(args.shift),
            pad_base=int(args.pad_base),
            title_prefix=f"{did} | ",
            subtitle=str(disease.get("disease_name") or "") or None,
        )

        fname = _safe_name(f"{gene_id}_{did}_ws{args.window_size}_core{args.out_len}.png")
        save_figure(fig, out_dir / fname, dpi=int(args.dpi))
        print(f"[OK] saved plot -> {out_dir/fname}")


if __name__ == "__main__":
    main()
