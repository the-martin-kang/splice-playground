from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .annotation import RefAnnotation
from .backend_client import BackendClient
from .genome import ReferenceGenome
from .inference import InferenceConfig, encode_sequences, predict_probs
from .model import load_model
from .scoring import calculate_variant_score
from .sequence import build_ref_alt_sequences_from_row
from .utils import with_chr_prefix

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
        raise SystemExit(
            "matplotlib is required for visualization. Install with: uv add matplotlib"
        ) from e

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
    from .plotting import plot_splicevar_example, save_figure  # local import

    p = argparse.ArgumentParser(description="Mission6-style visualization (local and/or backend sequences)")
    p.add_argument("--selected", required=True)
    p.add_argument("--annotation", required=True)
    p.add_argument("--fasta", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--backend-url", default=None)
    p.add_argument("--out-dir", default="plots_mission6")
    p.add_argument("--source", choices=["local", "backend", "both"], default="both")
    p.add_argument("--zoom", type=float, default=1.0, help="1..20 (larger => zoom in)")
    p.add_argument("--shift", type=int, default=0, help="genomic shift (nt) of view center")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--pad-base", type=int, default=1000, help="half-window when zoom=1")
    args = p.parse_args()

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
        ref_seq, alt_seq, mapping = build_ref_alt_sequences_from_row(
            row=r.to_dict(),
            genome=genome,
            tx_start_1b=tx_start,
            tx_end_1b=tx_end,
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
                "ref_seq": ref_seq,
                "alt_seq": alt_seq,
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
            payload = bc.get_window_4000(did, strict_ref_check=False)
            bref = payload.get("ref_seq_4000") or payload.get("ref_seq") or payload.get("ref_sequence")
            balt = payload.get("alt_seq_4000") or payload.get("alt_seq") or payload.get("alt_sequence")
            if isinstance(bref, str) and isinstance(balt, str):
                backend_rows_by_gene[gene] = {
                    **row,
                    "ref_seq": bref,
                    "alt_seq": balt,
                    "backend_payload": payload,
                }

    # Run inference for each source
    cfg = InferenceConfig(batch_size=8)

    def infer(rows: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        ref_seqs = [r["ref_seq"] for r in rows]
        alt_seqs = [r["alt_seq"] for r in rows]
        X_ref = encode_sequences(ref_seqs)
        X_alt = encode_sequences(alt_seqs)
        prob_ref = predict_probs(model, X_ref, cfg)
        prob_alt = predict_probs(model, X_alt, cfg)
        scores = calculate_variant_score(prob_ref, prob_alt)
        return prob_ref, prob_alt, scores

    prob_ref_local, prob_alt_local, scores_local = infer(local_rows)

    prob_ref_backend = prob_alt_backend = scores_backend = None
    backend_rows: Optional[List[Dict[str, Any]]] = None
    if args.backend_url and backend_rows_by_gene:
        # keep same order as local_rows for convenience
        backend_rows = []
        for row in local_rows:
            gene = row["gene"]
            if gene in backend_rows_by_gene:
                backend_rows.append(backend_rows_by_gene[gene])
            else:
                backend_rows.append(None)  # placeholder
        # infer only for genes with backend sequences
        rows_infer = [r for r in backend_rows if isinstance(r, dict)]
        prob_ref_b, prob_alt_b, scores_b = infer(rows_infer)
        # map back by gene
        prob_ref_backend = {}
        prob_alt_backend = {}
        scores_backend = {}
        j = 0
        for r in backend_rows:
            if isinstance(r, dict):
                g = r["gene"]
                prob_ref_backend[g] = prob_ref_b[j]
                prob_alt_backend[g] = prob_alt_b[j]
                scores_backend[g] = float(scores_b[j])
                j += 1

    # Write plots
    html_lines = [
        "<html><head><meta charset='utf-8'><title>Mission6-style plots</title></head><body>",
        "<h1>Mission6-style SpliceAI plots</h1>",
        f"<p>zoom={args.zoom}, shift={args.shift}, pad_base={args.pad_base}</p>",
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
            )
            fname = f"{_safe_name(gene)}_local.png"
            out_path = out_dir / fname
            save_figure(fig, str(out_path), dpi=args.dpi)
            html_lines.append(f"<h2>{gene} (LOCAL)</h2><img src='{fname}' style='max-width: 100%;'/>")

        # BACKEND plot
        if args.backend_url and args.source in ("backend", "both") and gene in backend_rows_by_gene and prob_ref_backend:
            ok_ref, idx_ref = _compare_sequences(row["ref_seq"], backend_rows_by_gene[gene]["ref_seq"])
            ok_alt, idx_alt = _compare_sequences(row["alt_seq"], backend_rows_by_gene[gene]["alt_seq"])
            subtitle = None
            if not (ok_ref and ok_alt):
                subtitle = f"Sequence mismatch: ref_idx0={idx_ref}, alt_idx0={idx_alt}"

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
                subtitle=subtitle,
            )
            fname = f"{_safe_name(gene)}_backend.png"
            out_path = out_dir / fname
            save_figure(fig, str(out_path), dpi=args.dpi)
            html_lines.append(f"<h2>{gene} (BACKEND)</h2><img src='{fname}' style='max-width: 100%;'/>")

    html_lines.append("</body></html>")
    (out_dir / "index.html").write_text("\n".join(html_lines), encoding="utf-8")
    print(f"[OK] wrote plots -> {out_dir}")
    print(f"[OK] open: {out_dir / 'index.html'}")

if __name__ == "__main__":
    main()
