from __future__ import annotations

import argparse
import json
from dataclasses import asdict
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
from .splice_sites import summarize_sites


def _load_selected(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    required = {"chrom", "pos", "ref", "alt", "gene", "strand"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"selected_gene.tsv missing columns: {sorted(missing)}")
    return df


def _compare_sequences(a: str, b: str) -> Tuple[bool, Optional[int]]:
    if a == b:
        return True, None
    # find first mismatch
    L = min(len(a), len(b))
    for i in range(L):
        if a[i] != b[i]:
            return False, i
    return False, L


def main() -> None:
    p = argparse.ArgumentParser(description="Mission6-style SpliceAI validation vs backend DB")
    p.add_argument("--selected", required=True, help="Path to selected_gene.tsv (6 genes list)")
    p.add_argument("--annotation", required=True, help="Path to Mission6_refannotation.tsv")
    p.add_argument("--fasta", required=True, help="Path to Mission6_refgenome.fa (or GRCh38 fasta)")
    p.add_argument("--model", required=True, help="Path to mission5.pt (SpliceAI weights)")
    p.add_argument("--backend-url", default=None, help="If set, compare with backend /window_4000 endpoint")
    p.add_argument("--out", default="validation_report.json", help="Output JSON report path")
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--donor-label-mode", choices=["intron_start", "exon_end"], default="intron_start")
    p.add_argument("--snap-k", type=int, default=5)
    p.add_argument("--top-k", type=int, default=5)
    args = p.parse_args()

    selected_df = _load_selected(args.selected)
    ann = RefAnnotation(args.annotation)
    genome = ReferenceGenome(args.fasta)

    # Build local sequences
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
                "chrom": str(r["chrom"]),
                "pos": int(r["pos"]),
                "strand": str(r["strand"]),
                "ref": str(r["ref"]),
                "alt": str(r["alt"]),
                "tx_start": tx_start,
                "tx_end": tx_end,
                "ref_seq_4000": ref_seq,
                "alt_seq_4000": alt_seq,
                "mapping": mapping,
            }
        )

    # Optionally pull backend sequences
    backend_map: Dict[str, Dict[str, Any]] = {}
    disease_id_by_gene: Dict[str, str] = {}
    if args.backend_url:
        bc = BackendClient(args.backend_url)
        diseases = bc.list_diseases()
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
            payload = bc.get_window_4000(did)
            backend_map[gene] = payload

    # Model inference
    model = load_model(args.model)

    ref_seqs = [r["ref_seq_4000"] for r in local_rows]
    alt_seqs = [r["alt_seq_4000"] for r in local_rows]
    X_ref = encode_sequences(ref_seqs)
    X_alt = encode_sequences(alt_seqs)

    cfg = InferenceConfig(batch_size=args.batch_size)
    prob_ref = predict_probs(model, X_ref, cfg)
    prob_alt = predict_probs(model, X_alt, cfg)
    scores = calculate_variant_score(prob_ref, prob_alt)

    report: Dict[str, Any] = {
        "inputs": {
            "selected": args.selected,
            "annotation": args.annotation,
            "fasta": args.fasta,
            "model": args.model,
            "backend_url": args.backend_url,
        },
        "variants": [],
    }

    for i, row in enumerate(local_rows):
        gene = row["gene"]
        mapping = row["mapping"]

        vrep: Dict[str, Any] = {
            "gene": gene,
            "chrom": row["chrom"],
            "pos_1b": row["pos"],
            "strand": row["strand"],
            "tx_start": row["tx_start"],
            "tx_end": row["tx_end"],
            "variant_score": float(scores[i]),
        }

        # Sequence compare
        if args.backend_url and gene in backend_map:
            b = backend_map[gene]
            bref = b.get("ref_seq_4000") or b.get("ref_seq") or b.get("ref_sequence")
            balt = b.get("alt_seq_4000") or b.get("alt_seq") or b.get("alt_sequence")
            if isinstance(bref, str) and isinstance(balt, str):
                ok_ref, idx_ref = _compare_sequences(row["ref_seq_4000"], bref)
                ok_alt, idx_alt = _compare_sequences(row["alt_seq_4000"], balt)
                vrep["backend_sequence_match"] = {
                    "ref": {"ok": ok_ref, "first_mismatch_idx0": idx_ref},
                    "alt": {"ok": ok_alt, "first_mismatch_idx0": idx_alt},
                }
            else:
                vrep["backend_sequence_match"] = {"error": "backend payload missing sequences"}

        # Splice site summary (ref)
        donor_sites_1b, acceptor_sites_1b = ann.splice_label_sites_1b(gene, donor_label_mode=args.donor_label_mode)

        sites = summarize_sites(
            seq_ref=row["ref_seq_4000"],
            prob_ref=prob_ref[i],
            mapping=mapping,
            donor_sites_1b=donor_sites_1b,
            acceptor_sites_1b=acceptor_sites_1b,
            top_k=args.top_k,
            snap_k=args.snap_k,
            donor_channel=1,
            acceptor_channel=2,
        )
        vrep["site_calls"] = {
            "donor": [asdict(x) for x in sites["donor"]],
            "acceptor": [asdict(x) for x in sites["acceptor"]],
        }

        report["variants"].append(vrep)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote report -> {args.out}")
    if args.backend_url:
        n_ok = sum(
            1
            for v in report["variants"]
            if v.get("backend_sequence_match", {}).get("ref", {}).get("ok") and v.get("backend_sequence_match", {}).get("alt", {}).get("ok")
        )
        print(f"[SEQ] backend matches: {n_ok}/{len(report['variants'])}")


if __name__ == "__main__":
    main()
