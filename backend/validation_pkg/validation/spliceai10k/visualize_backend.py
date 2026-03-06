from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..mission6.annotation import RefAnnotation
from ..mission6.backend_client import BackendClient
from ..mission6.genome import ReferenceGenome
from ..mission6.model import load_model
from ..mission6.sequence import build_ref_alt_sequences_from_row
from ..mission6.utils import with_chr_prefix

from .constants import IN_LENGTH_DEFAULT, OUT_LENGTH_DEFAULT, core_slice
from .inference import InferenceConfig, encode_sequences, predict_probs_center_crop
from .scoring import calculate_variant_score


def _load_selected(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    required = {"chrom", "pos", "ref", "alt", "gene", "strand"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"selected_gene.tsv missing columns: {sorted(missing)}")
    return df


def _ensure_matplotlib() -> None:
    try:
        import matplotlib  # noqa: F401
    except Exception as e:
        raise SystemExit("matplotlib is required for visualization. Install with: uv add matplotlib") from e


def _compare_sequences(a: str, b: str) -> Tuple[bool, Optional[int]]:
    if a == b:
        return True, None
    L = min(len(a), len(b))
    for i in range(L):
        if a[i] != b[i]:
            return False, i
    return False, L


def _safe_name(s: str) -> str:
    return "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in str(s)])


def main() -> None:
    _ensure_matplotlib()
    from ..mission6.plotting import plot_splicevar_example, save_figure  # local import

    p = argparse.ArgumentParser(description="SpliceAI-10k visualization (variant-centered core 5000)")
    p.add_argument("--selected", required=True)
    p.add_argument("--annotation", required=True)
    p.add_argument("--fasta", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--backend-url", default=None)
    p.add_argument("--out-dir", default="plots_spliceai10k")
    p.add_argument("--source", choices=["local", "backend", "both"], default="both")
    p.add_argument("--window-size", type=int, default=IN_LENGTH_DEFAULT)
    p.add_argument("--out-len", type=int, default=OUT_LENGTH_DEFAULT)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--device", default=None)
    p.add_argument("--zoom", type=float, default=1.0, help="1..20 (larger => zoom in)")
    p.add_argument("--shift", type=int, default=0, help="genomic shift (nt) of view center")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--pad-base", type=int, default=1000, help="half-window when zoom=1")
    args = p.parse_args()

    if args.out_len > args.window_size:
        raise SystemExit("--out-len must be <= --window-size")

    selected_df = _load_selected(args.selected)
    ann = RefAnnotation(args.annotation)
    genome = ReferenceGenome(args.fasta)
    model = load_model(args.model)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build LOCAL sequences
    local_rows: List[Dict[str, Any]] = []
    for _, r in selected_df.iterrows():
        gene = str(r["gene"])
        gene_row = ann.get_gene_row(gene)
        tx_start = int(gene_row["TX_START"])
        tx_end = int(gene_row["TX_END"])
        ref_seq_in, alt_seq_in, _ = build_ref_alt_sequences_from_row(
            row=r.to_dict(),
            genome=genome,
            tx_start_1b=tx_start,
            tx_end_1b=tx_end,
            input_length=int(args.window_size),
            check_ref=True,
        )
        local_rows.append(
            {
                "gene": gene,
                "chrom": with_chr_prefix(str(r["chrom"])),
                "pos": int(r["pos"]),
                "strand": str(r["strand"]),
                "ref": str(r["ref"]),
                "alt": str(r["alt"]),
                "tx_start": tx_start,
                "tx_end": tx_end,
                "ref_seq_in": ref_seq_in,
                "alt_seq_in": alt_seq_in,
            }
        )

    # Build BACKEND sequences (optional)
    backend_rows_by_gene: Dict[str, Dict[str, Any]] = {}
    if args.backend_url:
        bc = BackendClient(args.backend_url)
        diseases = bc.list_diseases()
        disease_id_by_gene: Dict[str, str] = {}
        for d in diseases:
            g = d.get("gene_id") or d.get("gene") or d.get("gene_symbol")
            did = d.get("disease_id")
            if g and did:
                disease_id_by_gene[str(g)] = str(did)

        for row in local_rows:
            gene = row["gene"]
            did = disease_id_by_gene.get(gene)
            if not did:
                continue
            payload = bc.get_window_4000(did, window_size=int(args.window_size), strict_ref_check=False)
            bref = payload.get("ref_seq_4000") or payload.get("ref_seq") or payload.get("ref_sequence")
            balt = payload.get("alt_seq_4000") or payload.get("alt_seq") or payload.get("alt_sequence")
            if isinstance(bref, str) and isinstance(balt, str):
                backend_rows_by_gene[gene] = {
                    **row,
                    "ref_seq_in": bref,
                    "alt_seq_in": balt,
                    "backend_payload": payload,
                }

    # Run inference for each source (core probs only)
    cfg = InferenceConfig(batch_size=int(args.batch_size), device=args.device)

    def infer(rows: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        ref_seqs = [r["ref_seq_in"] for r in rows]
        alt_seqs = [r["alt_seq_in"] for r in rows]
        X_ref = encode_sequences(ref_seqs)
        X_alt = encode_sequences(alt_seqs)
        prob_ref = predict_probs_center_crop(model, X_ref, in_length=int(args.window_size), out_length=int(args.out_len), cfg=cfg)
        prob_alt = predict_probs_center_crop(model, X_alt, in_length=int(args.window_size), out_length=int(args.out_len), cfg=cfg)
        scores = calculate_variant_score(prob_ref, prob_alt)
        return prob_ref, prob_alt, scores

    prob_ref_local, prob_alt_local, scores_local = infer(local_rows)

    prob_ref_backend = prob_alt_backend = scores_backend = None
    if args.backend_url and backend_rows_by_gene:
        rows_infer = [backend_rows_by_gene[r["gene"]] for r in local_rows if r["gene"] in backend_rows_by_gene]
        prob_ref_b, prob_alt_b, scores_b = infer(rows_infer)

        # map back by gene
        prob_ref_backend = {}
        prob_alt_backend = {}
        scores_backend = {}
        for j, r in enumerate(rows_infer):
            g = r["gene"]
            prob_ref_backend[g] = prob_ref_b[j]
            prob_alt_backend[g] = prob_alt_b[j]
            scores_backend[g] = float(scores_b[j])

    html_lines = [
        "<html><head><meta charset='utf-8'><title>SpliceAI-10k plots</title></head><body>",
        "<h1>SpliceAI-10k plots (core output)</h1>",
        f"<p>window_size={args.window_size}, out_len={args.out_len}, zoom={args.zoom}, shift={args.shift}, pad_base={args.pad_base}</p>",
    ]

    for i, row in enumerate(local_rows):
        gene = row["gene"]
        chrom = row["chrom"]
        pos = row["pos"]
        strand = row["strand"]
        ref = row["ref"]
        alt = row["alt"]

        gene_row = ann.get_gene_row(gene)
        exon_starts = gene_row["EXON_START"]
        exon_ends = gene_row["EXON_END"]

        subtitle = f"in={args.window_size} → out={args.out_len}"

        # LOCAL plot
        if args.source in ("local", "both"):
            fig = plot_splicevar_example(
                prob_ref_local[i],
                prob_alt_local[i],
                gene=gene,
                chrom=chrom,
                pos_1b=pos,
                strand=strand,
                ref=ref,
                alt=alt,
                variant_score=float(scores_local[i]),
                exon_starts=exon_starts,
                exon_ends=exon_ends,
                zoom=args.zoom,
                shift=args.shift,
                pad_base=args.pad_base,
                title_prefix="[LOCAL] ",
                subtitle=subtitle,
            )
            fname = f"{_safe_name(gene)}_local.png"
            save_figure(fig, str(out_dir / fname), dpi=args.dpi)
            html_lines.append(f"<h2>{gene} (LOCAL)</h2><img src='{fname}' style='max-width: 100%;'/>")

        # BACKEND plot
        if args.backend_url and args.source in ("backend", "both") and gene in backend_rows_by_gene and prob_ref_backend:
            ok_ref, idx_ref = _compare_sequences(row["ref_seq_in"], backend_rows_by_gene[gene]["ref_seq_in"])
            ok_alt, idx_alt = _compare_sequences(row["alt_seq_in"], backend_rows_by_gene[gene]["alt_seq_in"])
            sub2 = subtitle
            if not (ok_ref and ok_alt):
                sub2 += f" | SEQ mismatch: ref_idx0={idx_ref}, alt_idx0={idx_alt}"

            fig = plot_splicevar_example(
                prob_ref_backend[gene],
                prob_alt_backend[gene],
                gene=gene,
                chrom=chrom,
                pos_1b=pos,
                strand=strand,
                ref=ref,
                alt=alt,
                variant_score=float(scores_backend[gene]),
                exon_starts=exon_starts,
                exon_ends=exon_ends,
                zoom=args.zoom,
                shift=args.shift,
                pad_base=args.pad_base,
                title_prefix="[BACKEND] ",
                subtitle=sub2,
            )
            fname = f"{_safe_name(gene)}_backend.png"
            save_figure(fig, str(out_dir / fname), dpi=args.dpi)
            html_lines.append(f"<h2>{gene} (BACKEND)</h2><img src='{fname}' style='max-width: 100%;'/>")

    html_lines.append("</body></html>")
    (out_dir / "index.html").write_text("\n".join(html_lines), encoding="utf-8")
    print(f"[OK] wrote plots -> {out_dir}")
    print(f"[OK] open: {out_dir / 'index.html'}")


if __name__ == "__main__":
    main()
