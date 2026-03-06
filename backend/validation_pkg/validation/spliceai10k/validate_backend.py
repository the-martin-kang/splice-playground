from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..mission6.annotation import RefAnnotation
from ..mission6.backend_client import BackendClient
from ..mission6.genome import ReferenceGenome
from ..mission6.model import load_model
from ..mission6.sequence import build_ref_alt_sequences_from_row
from ..mission6.splice_sites import summarize_sites, calls_at_annotated_sites
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




def _motif_at_idx0(seq: str, idx0: int, kind: str, donor_label_mode: str = "exon_end") -> Optional[str]:
    """Canonical motif lookup using the SAME convention as mission6/splice_sites.py.

    - acceptor label at exon start: motif is seq[idx0-2:idx0] == 'AG'
    - donor label at exon end:     motif is seq[idx0+1:idx0+3] in {'GT','GC'}
      (for donor_label_mode='intron_start', motif is seq[idx0:idx0+2])
    """
    if kind == "acceptor":
        a = idx0 - 2
        b = idx0
        if a < 0 or b > len(seq):
            return None
        return seq[a:b].upper()
    # donor
    if donor_label_mode == "intron_start":
        a = idx0
        b = idx0 + 2
    else:
        a = idx0 + 1
        b = idx0 + 3
    if a < 0 or b > len(seq):
        return None
    return seq[a:b].upper()
def _compare_sequences(a: str, b: str) -> Tuple[bool, Optional[int]]:
    if a == b:
        return True, None
    L = min(len(a), len(b))
    for i in range(L):
        if a[i] != b[i]:
            return False, i
    return False, L


@dataclass(frozen=True)
class WindowMappingDynamic:
    """Index <-> genomic coordinate mapping for a *transcript-oriented* window.

    We follow the exact Mission6 convention:
      - Even length: center index is L//2 (right-center). seq[center_idx] corresponds to pos_1b.
      - '-' strand uses the Mission6 +1 shift inside fetch_seq, so the covered genomic range is
        asymmetric by 1nt (same as Mission6).
    """

    chrom: str
    pos_1b: int
    strand: str
    center_idx0: int

    def idx_to_genomic_1b(self, idx0: int) -> int:
        if self.strand == "+":
            return (self.pos_1b - self.center_idx0) + int(idx0)
        # transcript index increases while genomic coordinate decreases
        return (self.pos_1b + self.center_idx0) - int(idx0)

    def genomic_1b_to_idx(self, coord_1b: int) -> int:
        if self.strand == "+":
            return int(coord_1b) - (self.pos_1b - self.center_idx0)
        return (self.pos_1b + self.center_idx0) - int(coord_1b)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Validate SpliceAI-10k (15000->5000) against FASTA/annotation and optionally compare backend /window sequences"
    )
    p.add_argument("--selected", required=True, help="selected_gene.tsv")
    p.add_argument("--annotation", required=True, help="refannotation_with_canonical.tsv")
    p.add_argument("--fasta", required=True, help="GRCh38 fasta")
    p.add_argument("--model", required=True, help="trained model checkpoint (.pt)")
    p.add_argument("--backend-url", default=None, help="Optional backend URL for /window sequence comparison")
    p.add_argument("--out", default="report_spliceai10k.json", help="Output report json")

    p.add_argument("--window-size", type=int, default=IN_LENGTH_DEFAULT, help="Model input length (default: 15000)")
    p.add_argument("--out-len", type=int, default=OUT_LENGTH_DEFAULT, help="Model output core length (default: 5000)")

    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--device", default=None, help="cpu/cuda/mps (optional)")

    p.add_argument("--donor-label-mode", choices=["intron_start", "exon_end"], default="exon_end")
    p.add_argument("--snap-k", type=int, default=2, help="snap predicted sites to canonical motifs within ±k")
    p.add_argument("--top-k", type=int, default=10, help="top-k predicted sites to report per channel")
    args = p.parse_args()

    in_len = int(args.window_size)
    out_len = int(args.out_len)
    if out_len > in_len:
        raise SystemExit("--out-len must be <= --window-size")
    if (in_len % 2) != 0:
        raise SystemExit("--window-size must be even for Mission6-style centering (use even numbers like 15000).")

    core_sl = core_slice(in_len, out_len)
    core_start = int(core_sl.start or 0)
    center_in = in_len // 2
    center_core = center_in - core_start

    selected_df = _load_selected(args.selected)
    ann = RefAnnotation(args.annotation)
    genome = ReferenceGenome(args.fasta)
    model = load_model(args.model)

    # LOCAL sequences
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
            input_length=in_len,
            check_ref=True,
        )

        ref_seq_core = ref_seq_in[core_sl]
        alt_seq_core = alt_seq_in[core_sl]

        chrom = with_chr_prefix(str(r["chrom"]))
        pos_1b = int(r["pos"])
        strand = str(r["strand"])

        mapping_core = WindowMappingDynamic(
            chrom=chrom,
            pos_1b=pos_1b,
            strand=strand,
            center_idx0=center_core,
        )

        local_rows.append(
            {
                "gene": gene,
                "chrom": chrom,
                "pos_1b": pos_1b,
                "strand": strand,
                "ref": str(r["ref"]),
                "alt": str(r["alt"]),
                "tx_start": tx_start,
                "tx_end": tx_end,
                "ref_seq_in": ref_seq_in,
                "alt_seq_in": alt_seq_in,
                "ref_seq_core": ref_seq_core,
                "alt_seq_core": alt_seq_core,
                "mapping_core": mapping_core,
            }
        )

    # BACKEND sequences (optional)
    backend_payload_by_gene: Dict[str, Dict[str, Any]] = {}
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
            payload = bc.get_window_4000(did, window_size=in_len, strict_ref_check=False)
            backend_payload_by_gene[gene] = payload

    # run inference (core probs only)
    cfg = InferenceConfig(batch_size=int(args.batch_size), device=args.device)
    ref_seqs = [r["ref_seq_in"] for r in local_rows]
    alt_seqs = [r["alt_seq_in"] for r in local_rows]

    X_ref = encode_sequences(ref_seqs)
    X_alt = encode_sequences(alt_seqs)

    prob_ref = predict_probs_center_crop(model, X_ref, in_length=in_len, out_length=out_len, cfg=cfg)
    prob_alt = predict_probs_center_crop(model, X_alt, in_length=in_len, out_length=out_len, cfg=cfg)
    scores = calculate_variant_score(prob_ref, prob_alt)

    report_variants: List[Dict[str, Any]] = []

    for i, row in enumerate(local_rows):
        gene = row["gene"]
        chrom = row["chrom"]
        pos_1b = row["pos_1b"]
        strand = row["strand"]
        ref = row["ref"]
        alt = row["alt"]

        # canonical sites + kinds (exonN_donor/exonN_acceptor)
        donor_sites, acceptor_sites, donor_kind_by_1b, acceptor_kind_by_1b = ann.splice_label_sites_with_kinds_1b(
            gene, donor_label_mode=args.donor_label_mode
        )

        sites = summarize_sites(
            seq_ref=row["ref_seq_core"],
            prob_ref=prob_ref[i],
            mapping=row["mapping_core"],
            donor_sites_1b=donor_sites,
            acceptor_sites_1b=acceptor_sites,
            donor_kind_by_1b=donor_kind_by_1b,
            acceptor_kind_by_1b=acceptor_kind_by_1b,
            donor_label_mode=args.donor_label_mode,
            top_k=int(args.top_k),
            snap_k=int(args.snap_k),
            donor_channel=2,
            acceptor_channel=1,
        )
        calls = {
            "donor": [asdict(x) for x in sites["donor"]],
            "acceptor": [asdict(x) for x in sites["acceptor"]],
        }


        # --- annotated-site view (1 call per exon boundary inside the window) ---
        annotated_ref = calls_at_annotated_sites(
            seq_ref=row["ref_seq_core"],
            prob_ref=prob_ref[i],
            mapping=row["mapping_core"],
            donor_sites_1b=donor_sites,
            acceptor_sites_1b=acceptor_sites,
            donor_kind_by_1b=donor_kind_by_1b,
            acceptor_kind_by_1b=acceptor_kind_by_1b,
            donor_label_mode=args.donor_label_mode,
            snap_k=int(args.snap_k),
            donor_channel=2,
            acceptor_channel=1,
        )

        annotated_calls: Dict[str, List[Dict[str, Any]]] = {"donor": [], "acceptor": []}

        # donor
        for c in annotated_ref["donor"]:
            d = asdict(c)
            idx0 = int(d["idx0"])
            ref_p = float(d.pop("prob"))
            motif_ref = d.pop("motif", None)
            alt_p = float(prob_alt[i, 2, idx0])
            motif_alt = _motif_at_idx0(row["alt_seq_core"], idx0, "donor", donor_label_mode=args.donor_label_mode)
            d.update(
                {
                    "motif_ref": motif_ref,
                    "motif_alt": motif_alt,
                    "prob_ref": ref_p,
                    "prob_alt": alt_p,
                    "delta_prob": alt_p - ref_p,
                }
            )
            annotated_calls["donor"].append(d)

        # acceptor
        for c in annotated_ref["acceptor"]:
            d = asdict(c)
            idx0 = int(d["idx0"])
            ref_p = float(d.pop("prob"))
            motif_ref = d.pop("motif", None)
            alt_p = float(prob_alt[i, 1, idx0])
            motif_alt = _motif_at_idx0(row["alt_seq_core"], idx0, "acceptor", donor_label_mode=args.donor_label_mode)
            d.update(
                {
                    "motif_ref": motif_ref,
                    "motif_alt": motif_alt,
                    "prob_ref": ref_p,
                    "prob_alt": alt_p,
                    "delta_prob": alt_p - ref_p,
                }
            )
            annotated_calls["acceptor"].append(d)

        backend_match = None
        if gene in backend_payload_by_gene:
            payload = backend_payload_by_gene[gene]
            bref = payload.get("ref_seq_4000") or payload.get("ref_seq") or payload.get("ref_sequence")
            balt = payload.get("alt_seq_4000") or payload.get("alt_seq") or payload.get("alt_sequence")
            if isinstance(bref, str) and isinstance(balt, str):
                ok_ref, idx_ref = _compare_sequences(row["ref_seq_in"], bref)
                ok_alt, idx_alt = _compare_sequences(row["alt_seq_in"], balt)
                backend_match = {
                    "ref": {"ok": ok_ref, "first_mismatch_idx0": idx_ref, "len": len(bref)},
                    "alt": {"ok": ok_alt, "first_mismatch_idx0": idx_alt, "len": len(balt)},
                }
            else:
                backend_match = {"error": "backend payload missing sequences"}

        report_variants.append(
            {
                "gene": gene,
                "chrom": chrom,
                "pos_1b": pos_1b,
                "strand": strand,
                "ref": ref,
                "alt": alt,
                "tx_start": row["tx_start"],
                "tx_end": row["tx_end"],
                "window_size_in": in_len,
                "out_len_core": out_len,
                "core_start_idx0_in_window": core_start,
                "center_idx0_in_window": center_in,
                "center_idx0_in_core": center_core,
                "variant_score": float(scores[i]),
                "backend_sequence_match": backend_match,
                "site_calls": calls,
                "site_calls_annotated": annotated_calls,
            }
        )

    out_obj = {
        "meta": {
            "selected": args.selected,
            "annotation": args.annotation,
            "fasta": args.fasta,
            "model": args.model,
            "backend_url": args.backend_url,
            "window_size_in": in_len,
            "out_len_core": out_len,
            "core_start_idx0_in_window": core_start,
            "center_idx0_in_window": center_in,
            "center_idx0_in_core": center_core,
            "batch_size": int(args.batch_size),
            "device": args.device,
            "donor_label_mode": args.donor_label_mode,
            "snap_k": int(args.snap_k),
            "top_k": int(args.top_k),
        },
        "variants": report_variants,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)

    # quick summary
    if args.backend_url:
        n_ok = sum(
            1
            for v in report_variants
            if v.get("backend_sequence_match", {}).get("ref", {}).get("ok") and v.get("backend_sequence_match", {}).get("alt", {}).get("ok")
        )
        print(f"[SEQ] backend matches: {n_ok}/{len(report_variants)}")

    print(f"[OK] wrote report -> {args.out}")


if __name__ == "__main__":
    main()
