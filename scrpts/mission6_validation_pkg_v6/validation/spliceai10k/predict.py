
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from pyfaidx import Fasta

from ..mission6.annotation import RefAnnotation
from ..mission6.utils import rc, complement_base, with_chr_prefix, without_chr_prefix
from ..mission6.constants import CANONICAL_ACCEPTOR_MOTIF, CANONICAL_DONOR_MOTIFS


# -------------------------
# Helpers: FASTA fetch
# -------------------------

class Genome:
    """Simple FASTA reader (no Mission6 '-' offset hack)."""

    def __init__(self, fasta_path: str) -> None:
        self.fa = Fasta(fasta_path, as_raw=True, sequence_always_upper=True)
        self._keys = set(self.fa.keys())
        # detect whether fasta keys use 'chr' prefix
        self._has_chr = any(k.startswith("chr") for k in list(self._keys)[:10])

    def _normalize_key(self, chrom: str) -> str:
        c = str(chrom).strip()
        if self._has_chr:
            c = with_chr_prefix(c)
        else:
            c = without_chr_prefix(c)
        if c in self._keys:
            return c
        # fallback toggle
        alt = without_chr_prefix(c) if c.startswith("chr") else with_chr_prefix(c)
        if alt in self._keys:
            return alt
        raise KeyError(f"Chromosome {chrom!r} not found in FASTA keys")

    def fetch_1based_inclusive(self, chrom: str, start_1b: int, end_1b: int) -> str:
        """Fetch [start_1b, end_1b] inclusive, 1-based."""
        if start_1b < 1:
            raise ValueError("start_1b must be >= 1")
        if end_1b < start_1b:
            raise ValueError("end_1b must be >= start_1b")
        key = self._normalize_key(chrom)
        # pyfaidx uses 0-based slices, end exclusive
        start0 = start_1b - 1
        end0 = end_1b
        return str(self.fa[key][start0:end0])


# -------------------------
# Helpers: encoding
# -------------------------

_BASE_TO_IDX = np.full(256, 4, dtype=np.uint8)  # default N/other -> 4
_BASE_TO_IDX[ord("A")] = 0
_BASE_TO_IDX[ord("C")] = 1
_BASE_TO_IDX[ord("G")] = 2
_BASE_TO_IDX[ord("T")] = 3
_BASE_TO_IDX[ord("N")] = 4

def encode_seq_to_onehot(seq: str, device: torch.device) -> torch.Tensor:
    """Return float32 one-hot tensor [1,4,L] (N -> all zeros)."""
    b = np.frombuffer(seq.encode("ascii"), dtype=np.uint8)
    codes = _BASE_TO_IDX[b]  # uint8 [L], 0..4
    L = int(codes.shape[0])

    x = np.zeros((4, L), dtype=np.float32)
    for base_idx in range(4):
        mask = codes == base_idx
        if mask.any():
            x[base_idx, mask] = 1.0

    xt = torch.from_numpy(x).unsqueeze(0).to(device)  # [1,4,L]
    return xt


# -------------------------
# Model loading
# -------------------------

def load_spliceai10k_model(model_path: str, device: torch.device) -> torch.nn.Module:
    """Load your ResBlock-based SpliceAI model checkpoint (no external deps).

    We deliberately avoid importing `spliceai_pytorch` to keep the validation pkg light.
    Supported checkpoint formats:
      - state_dict only
      - dict with keys: state_dict / model_state_dict / model
    """
    from ..mission6.model import load_model  # reuse the same architecture used in your notebooks
    return load_model(model_path, device=device)

# -------------------------
# Annotation helpers (exon numbering + sites)
# -------------------------

@dataclass(frozen=True)
class GeneInfo:
    gene: str
    chrom: str
    strand: Literal["+", "-"]
    tx_start_1b: int
    tx_end_1b: int
    exons_1b: List[Tuple[int, int]]  # transcript-order exons: (start_1b, end_1b)

    @property
    def tx_len(self) -> int:
        return int(self.tx_end_1b - self.tx_start_1b + 1)

    def tx_idx0_from_genomic_1b(self, pos_1b: int) -> int:
        if self.strand == "+":
            return int(pos_1b - self.tx_start_1b)
        return int(self.tx_end_1b - pos_1b)

    def genomic_1b_from_tx_idx0(self, idx0: int) -> int:
        if self.strand == "+":
            return int(self.tx_start_1b + idx0)
        return int(self.tx_end_1b - idx0)

    def exon_bounds_tx_idx0(self) -> List[Tuple[int, int]]:
        """Return exon bounds in transcript-oriented idx0 (inclusive)."""
        out: List[Tuple[int, int]] = []
        for s1b, e1b in self.exons_1b:
            if self.strand == "+":
                s0 = s1b - self.tx_start_1b
                e0 = e1b - self.tx_start_1b
            else:
                # transcript idx0 uses reversed genomic coordinate
                s0 = self.tx_end_1b - e1b
                e0 = self.tx_end_1b - s1b
            out.append((int(s0), int(e0)))
        out.sort(key=lambda x: x[0])
        return out

    def internal_splice_sites_tx_idx0(
        self,
        *,
        donor_label_mode: Literal["exon_end", "intron_start"] = "exon_end",
    ) -> Tuple[List[int], List[int], Dict[int, str], Dict[int, str]]:
        """Return (donor_idx0, acceptor_idx0, donor_kind, acceptor_kind) in transcript idx0.

        Kinds are exon-based:
          - donor for exon i: exon{i}_donor
          - acceptor for exon j: exon{j}_acceptor

        Only internal junctions are returned (skip exon1 acceptor, last exon donor).
        """
        exon_bounds = self.exon_bounds_tx_idx0()
        n_exons = len(exon_bounds)

        donor_sites: List[int] = []
        acceptor_sites: List[int] = []
        donor_kind: Dict[int, str] = {}
        acceptor_kind: Dict[int, str] = {}

        for exon_idx, (s0, e0) in enumerate(exon_bounds):
            exon_num = exon_idx + 1

            if exon_idx > 0:
                # acceptor label at exon start
                acceptor_sites.append(int(s0))
                acceptor_kind[int(s0)] = f"exon{exon_num}_acceptor"

            if exon_idx < (n_exons - 1):
                if donor_label_mode == "exon_end":
                    don0 = int(e0)
                else:
                    # intron_start: first intron base after exon end => e0+1
                    don0 = int(e0 + 1)
                donor_sites.append(int(don0))
                donor_kind[int(don0)] = f"exon{exon_num}_donor"

        return donor_sites, acceptor_sites, donor_kind, acceptor_kind


def build_gene_info(ann: RefAnnotation, gene: str) -> GeneInfo:
    r = ann.get_gene_row(gene)
    chrom = str(r["CHROM"])
    strand = str(r["STRAND"])
    tx_start = int(r["TX_START"])
    tx_end = int(r["TX_END"])
    exon_starts = list(map(int, r["EXON_START"]))
    exon_ends = list(map(int, r["EXON_END"]))

    if len(exon_starts) != len(exon_ends):
        raise ValueError(f"EXON_START/EXON_END length mismatch for gene={gene}")

    exons = list(zip(exon_starts, exon_ends))
    # order exons by transcript direction (matches RefAnnotation.splice_label_sites_1b)
    exons.sort(key=lambda x: x[0], reverse=(strand == "-"))

    return GeneInfo(
        gene=str(gene),
        chrom=str(chrom),
        strand=strand,  # type: ignore
        tx_start_1b=tx_start,
        tx_end_1b=tx_end,
        exons_1b=[(int(s), int(e)) for (s, e) in exons],
    )


# -------------------------
# Splice site calling
# -------------------------

@dataclass
class SiteCall:
    kind: str  # e.g. "exon7_donor"
    site_type: Literal["donor", "acceptor"]
    idx0: int  # index in OUTPUT array (0-based)
    tx_idx0: int  # index in TRANSCRIPT (gene) coordinates (0-based, transcript direction)
    genomic_1b: int
    prob: float

    motif: Optional[str] = None
    snapped_from_idx0: Optional[int] = None

    cut_left_tx_idx0: Optional[int] = None
    cut_right_tx_idx0: Optional[int] = None
    cut_left_genomic_1b: Optional[int] = None
    cut_right_genomic_1b: Optional[int] = None

    nearest_annot_kind: Optional[str] = None
    nearest_annot_tx_idx0: Optional[int] = None
    delta_to_nearest_annot: Optional[int] = None


def _motif_at(seq: str, idx0: int, site_type: str, donor_label_mode: str) -> Optional[str]:
    L = len(seq)
    if site_type == "acceptor":
        if 2 <= idx0 <= L:
            return seq[idx0 - 2 : idx0]
        return None
    if site_type == "donor":
        if donor_label_mode == "exon_end":
            if 0 <= idx0 <= L - 3:
                return seq[idx0 + 1 : idx0 + 3]
            return None
        # intron_start: motif starts at idx0
        if 0 <= idx0 <= L - 2:
            return seq[idx0 : idx0 + 2]
        return None
    raise ValueError("site_type must be donor/acceptor")


def _cut_edges_tx(seq_len: int, tx_idx0: int, site_type: str, donor_label_mode: str) -> Tuple[Optional[int], Optional[int]]:
    # cut is between two transcript indices
    if site_type == "acceptor":
        if tx_idx0 - 1 < 0 or tx_idx0 >= seq_len:
            return None, None
        return tx_idx0 - 1, tx_idx0
    if site_type == "donor":
        if donor_label_mode == "exon_end":
            if tx_idx0 < 0 or tx_idx0 + 1 >= seq_len:
                return None, None
            return tx_idx0, tx_idx0 + 1
        # intron_start: cut is between (tx_idx0-1) | (tx_idx0)
        if tx_idx0 - 1 < 0 or tx_idx0 >= seq_len:
            return None, None
        return tx_idx0 - 1, tx_idx0
    raise ValueError("site_type must be donor/acceptor")


def _snap_to_canonical(
    seq_out: str,
    probs: np.ndarray,
    idx0: int,
    site_type: Literal["donor", "acceptor"],
    *,
    donor_label_mode: str,
    snap_k: int,
) -> Tuple[int, float, Optional[str], Optional[int]]:
    """Return (best_idx0, best_prob, motif, snapped_from_idx0)."""
    L = len(seq_out)

    def is_canonical(m: Optional[str]) -> bool:
        if not m:
            return False
        if site_type == "donor":
            return m in CANONICAL_DONOR_MOTIFS
        return m == CANONICAL_ACCEPTOR_MOTIF

    candidates: List[int] = []
    for d in range(-snap_k, snap_k + 1):
        j = idx0 + d
        if not (0 <= j < L):
            continue
        m = _motif_at(seq_out, j, site_type, donor_label_mode=donor_label_mode)
        if is_canonical(m):
            candidates.append(j)

    snapped_from: Optional[int] = None
    best_idx = int(idx0)
    best_prob = float(probs[idx0]) if 0 <= idx0 < L else float("nan")

    if candidates:
        snapped_from = int(idx0)
        best_idx = int(max(candidates, key=lambda j: float(probs[j])))
        best_prob = float(probs[best_idx])

    motif = _motif_at(seq_out, best_idx, site_type, donor_label_mode=donor_label_mode)
    return best_idx, best_prob, motif, snapped_from


def _nearest_annot(tx_idx0: int, annot_sites: List[int]) -> Optional[int]:
    if not annot_sites:
        return None
    return int(min(annot_sites, key=lambda s: abs(int(s) - int(tx_idx0))))


def call_top_sites(
    *,
    gene_info: GeneInfo,
    seq_out: str,
    acceptor_probs: np.ndarray,
    donor_probs: np.ndarray,
    out_tx_start_idx0: int,
    donor_label_mode: str,
    donor_kind_by_tx: Dict[int, str],
    acceptor_kind_by_tx: Dict[int, str],
    top_k: int,
    snap_k: int,
) -> Dict[str, List[SiteCall]]:
    """Return top-k calls for acceptor/donor channels (deduped after snapping)."""
    out_len = len(seq_out)
    if acceptor_probs.shape[0] != out_len or donor_probs.shape[0] != out_len:
        raise ValueError("prob length mismatch with seq_out")

    def build_calls(site_type: Literal["donor", "acceptor"]) -> List[SiteCall]:
        probs = donor_probs if site_type == "donor" else acceptor_probs
        take_n = min(out_len, max(top_k * 50, 50))
        cand = np.argsort(-probs)[:take_n]

        by_idx: Dict[int, SiteCall] = {}
        annot_sites_tx = list((donor_kind_by_tx if site_type == "donor" else acceptor_kind_by_tx).keys())

        for raw_i in cand:
            raw_i = int(raw_i)

            snap_i, snap_prob, motif, snapped_from = _snap_to_canonical(
                seq_out, probs, raw_i, site_type, donor_label_mode=donor_label_mode, snap_k=snap_k
            )

            tx_idx0 = int(out_tx_start_idx0 + snap_i)
            genomic_1b = gene_info.genomic_1b_from_tx_idx0(tx_idx0)

            # nearest annotation site (in tx_idx0)
            near_tx = _nearest_annot(tx_idx0, annot_sites_tx)
            near_kind = None
            delta = None
            if near_tx is not None:
                delta = int(tx_idx0 - near_tx)
                if site_type == "donor":
                    near_kind = donor_kind_by_tx.get(int(near_tx))
                else:
                    near_kind = acceptor_kind_by_tx.get(int(near_tx))

            # Choose "kind" for output: if we have a nearby annot kind, use it; else fallback
            kind = near_kind or ("donor" if site_type == "donor" else "acceptor")

            cut_l_tx, cut_r_tx = _cut_edges_tx(gene_info.tx_len, tx_idx0, site_type, donor_label_mode=donor_label_mode)
            cut_l_g = gene_info.genomic_1b_from_tx_idx0(cut_l_tx) if cut_l_tx is not None else None
            cut_r_g = gene_info.genomic_1b_from_tx_idx0(cut_r_tx) if cut_r_tx is not None else None

            call = SiteCall(
                kind=str(kind),
                site_type=site_type,
                idx0=int(snap_i),
                tx_idx0=int(tx_idx0),
                genomic_1b=int(genomic_1b),
                prob=float(snap_prob),
                motif=motif,
                snapped_from_idx0=snapped_from,
                cut_left_tx_idx0=cut_l_tx,
                cut_right_tx_idx0=cut_r_tx,
                cut_left_genomic_1b=cut_l_g,
                cut_right_genomic_1b=cut_r_g,
                nearest_annot_kind=near_kind,
                nearest_annot_tx_idx0=near_tx,
                delta_to_nearest_annot=delta,
            )

            prev = by_idx.get(int(call.idx0))
            if (prev is None) or (call.prob > prev.prob):
                by_idx[int(call.idx0)] = call

        calls = sorted(by_idx.values(), key=lambda x: float(x.prob), reverse=True)[:top_k]
        return calls

    return {"donor": build_calls("donor"), "acceptor": build_calls("acceptor")}


# -------------------------
# Prediction runners
# -------------------------

def _softmax_probs(logits: torch.Tensor) -> np.ndarray:
    """Return numpy probs [3, L_out]."""
    if logits.ndim != 3:
        raise ValueError(f"Expected logits [B, C, L], got {tuple(logits.shape)}")
    if logits.shape[1] != 3:
        # maybe [B, L, C]
        if logits.shape[2] == 3:
            logits = logits.permute(0, 2, 1)
        else:
            raise ValueError(f"Unexpected logits shape {tuple(logits.shape)}")
    probs = F.softmax(logits, dim=1)[0].detach().cpu().numpy().astype(np.float32)  # [3,L]
    return probs


def predict_probs_for_input(
    model: torch.nn.Module,
    seq_in: str,
    device: torch.device,
) -> np.ndarray:
    x = encode_seq_to_onehot(seq_in, device=device)
    with torch.no_grad():
        logits = model(x)
    return _softmax_probs(logits)


def build_transcript_seq(genome: Genome, gene_info: GeneInfo) -> str:
    # Fetch genomic region and orient to transcript direction
    seq = genome.fetch_1based_inclusive(gene_info.chrom, gene_info.tx_start_1b, gene_info.tx_end_1b)
    if gene_info.strand == "-":
        seq = rc(seq)
    return seq.upper()


def build_full_gene_inputs(
    transcript_seq: str,
    *,
    flank_each: int,
    var_tx_idx0: int,
    ref_base: str,
    alt_base: str,
) -> Tuple[str, str, int]:
    """Return (ref_input, alt_input, out_tx_start_idx0). Output covers full gene (tx_idx0 0..L-1)."""
    pad = "N" * flank_each
    ref_in = pad + transcript_seq + pad
    alt_in = list(ref_in)

    input_var_idx0 = flank_each + var_tx_idx0
    expected_ref = ref_in[input_var_idx0]
    if expected_ref != ref_base:
        # still allow, but this is worth warning at higher level
        pass
    alt_in[input_var_idx0] = alt_base
    alt_in_str = "".join(alt_in)

    return ref_in, alt_in_str, 0  # output starts at transcript idx0 0


def build_window_inputs(
    transcript_seq: str,
    *,
    input_len: int,
    core_len: int,
    flank_each: int,
    var_tx_idx0: int,
    ref_base: str,
    alt_base: str,
) -> Tuple[str, str, str, str, int]:
    """Return (ref_in, alt_in, ref_out_core_seq, alt_out_core_seq, out_tx_start_idx0)."""
    if input_len != core_len + flank_each * 2:
        raise ValueError("input_len must equal core_len + 2*flank_each")

    # center rule: for even, choose right center index (same as your FastAPI window rule)
    input_center = input_len // 2
    core_center = core_len // 2

    core_start_tx = var_tx_idx0 - core_center
    input_start_tx = core_start_tx - flank_each
    input_end_tx = input_start_tx + input_len

    # slice with N-padding
    left_pad = max(0, -input_start_tx)
    right_pad = max(0, input_end_tx - len(transcript_seq))

    s0 = max(0, input_start_tx)
    e0 = min(len(transcript_seq), input_end_tx)

    base = ("N" * left_pad) + transcript_seq[s0:e0] + ("N" * right_pad)
    assert len(base) == input_len, (len(base), input_len)

    ref_in = base
    alt_in = list(base)

    expected_ref = ref_in[input_center]
    if expected_ref != ref_base:
        # still allow; caller can decide strictness
        pass

    alt_in[input_center] = alt_base
    alt_in_str = "".join(alt_in)

    # output corresponds to the central core_len positions
    out_start = flank_each
    out_end = flank_each + core_len
    ref_out = ref_in[out_start:out_end]
    alt_out = alt_in_str[out_start:out_end]
    out_tx_start_idx0 = int(core_start_tx)

    return ref_in, alt_in_str, ref_out, alt_out, out_tx_start_idx0


def _round_floats(x: np.ndarray, ndigits: int = 6) -> List[float]:
    # small helper to reduce JSON size
    return [round(float(v), ndigits) for v in x.tolist()]


def main() -> None:
    p = argparse.ArgumentParser(description="SpliceAI-10k inference JSON dumper (gene-wide or SNV-centered core)")
    p.add_argument("--selected", required=True, help="selected_gene.tsv (chrom,pos,ref,alt,gene,strand)")
    p.add_argument("--annotation", required=True, help="refannotation_with_canonical.tsv (or Mission6_refannotation.tsv)")
    p.add_argument("--fasta", required=True, help="GRCh38.primary_assembly.genome.fa")
    p.add_argument("--model", required=True, help="trained spliceai10k checkpoint (.pt)")
    p.add_argument("--out", default="spliceai10k_report.json", help="output json path")
    p.add_argument("--mode", choices=["gene", "window", "both"], default="both")
    p.add_argument("--flank", type=int, default=10000, help="total flank (left+right). 10k model => 10000")
    p.add_argument("--core-len", type=int, default=5000, help="output core length. 10k model training => 5000")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--snap-k", type=int, default=5)
    p.add_argument("--donor-label-mode", choices=["exon_end", "intron_start"], default="exon_end")
    p.add_argument("--include-tracks", action="store_true", help="include per-position prob arrays (can be large)")
    p.add_argument("--strict-ref-check", action="store_true", help="error if expected ref base mismatches at variant")
    args = p.parse_args()

    flank_total = int(args.flank)
    if flank_total % 2 != 0:
        raise SystemExit("--flank must be even (left/right equal)")
    flank_each = flank_total // 2
    core_len = int(args.core_len)
    input_len = int(core_len + flank_total)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    selected_df = pd.read_csv(args.selected, sep="\t")
    required = {"chrom", "pos", "ref", "alt", "gene", "strand"}
    missing = required - set(selected_df.columns)
    if missing:
        raise SystemExit(f"selected file missing columns: {sorted(missing)}")

    ann = RefAnnotation(args.annotation)
    genome = Genome(args.fasta)
    model = load_spliceai10k_model(args.model, device=device)

    report: Dict[str, Any] = {
        "inputs": {
            "selected": args.selected,
            "annotation": args.annotation,
            "fasta": args.fasta,
            "model": args.model,
            "mode": args.mode,
            "flank_total": flank_total,
            "core_len": core_len,
            "input_len": input_len,
            "donor_label_mode": args.donor_label_mode,
            "top_k": args.top_k,
            "snap_k": args.snap_k,
            "device": str(device),
        },
        "variants": [],
    }

    for _, row in selected_df.iterrows():
        gene = str(row["gene"])
        chrom = str(row["chrom"])
        pos_1b = int(row["pos"])
        strand = str(row["strand"])
        ref = str(row["ref"]).upper()
        alt = str(row["alt"]).upper()

        ginfo = build_gene_info(ann, gene)

        # sanity: selected file and annotation should agree on strand
        if strand != ginfo.strand:
            # still allow, but log it in report
            pass

        transcript_seq = build_transcript_seq(genome, ginfo)

        var_tx_idx0 = ginfo.tx_idx0_from_genomic_1b(pos_1b)

        # prepare exon-based site kinds in transcript idx0
        donor_sites_tx, acceptor_sites_tx, donor_kind_by_tx, acceptor_kind_by_tx = ginfo.internal_splice_sites_tx_idx0(
            donor_label_mode=args.donor_label_mode  # type: ignore
        )

        vre: Dict[str, Any] = {
            "gene": gene,
            "chrom": chrom,
            "pos_1b": pos_1b,
            "strand": strand,
            "ref": ref,
            "alt": alt,
            "tx_start": ginfo.tx_start_1b,
            "tx_end": ginfo.tx_end_1b,
            "tx_len": ginfo.tx_len,
            "var_tx_idx0": var_tx_idx0,
        }

        # verify ref base at variant in transcript sequence
        actual_ref_tx = transcript_seq[var_tx_idx0] if 0 <= var_tx_idx0 < len(transcript_seq) else None
        vre["actual_ref_in_transcript"] = actual_ref_tx
        vre["ref_matches_transcript"] = (actual_ref_tx == ref)

        if args.strict_ref_check and (actual_ref_tx != ref):
            raise SystemExit(f"[{gene}] ref mismatch at variant: expected {ref}, got {actual_ref_tx}")

        results: Dict[str, Any] = {}

        # -------------- mode: gene-wide --------------
        if args.mode in {"gene", "both"}:
            ref_in, alt_in, out_tx_start = build_full_gene_inputs(
                transcript_seq,
                flank_each=flank_each,
                var_tx_idx0=var_tx_idx0,
                ref_base=ref,
                alt_base=alt,
            )
            prob_ref = predict_probs_for_input(model, ref_in, device=device)  # [3, L_out]
            prob_alt = predict_probs_for_input(model, alt_in, device=device)

            # output corresponds to full transcript (length tx_len)
            out_seq_ref = transcript_seq
            out_seq_alt = transcript_seq[:var_tx_idx0] + alt + transcript_seq[var_tx_idx0 + 1 :]

            acceptor_ref = prob_ref[1]
            donor_ref = prob_ref[2]
            acceptor_alt = prob_alt[1]
            donor_alt = prob_alt[2]

            # annotated sites (internal only)
            annot_sites: List[Dict[str, Any]] = []
            for tx0, kind in sorted(acceptor_kind_by_tx.items(), key=lambda x: x[0]):
                annot_sites.append(
                    {
                        "kind": kind,
                        "site_type": "acceptor",
                        "tx_idx0": int(tx0),
                        "genomic_1b": int(ginfo.genomic_1b_from_tx_idx0(int(tx0))),
                        "prob_ref": float(acceptor_ref[int(tx0)]),
                        "prob_alt": float(acceptor_alt[int(tx0)]),
                        "delta": float(acceptor_alt[int(tx0)] - acceptor_ref[int(tx0)]),
                    }
                )
            for tx0, kind in sorted(donor_kind_by_tx.items(), key=lambda x: x[0]):
                if 0 <= int(tx0) < ginfo.tx_len:
                    annot_sites.append(
                        {
                            "kind": kind,
                            "site_type": "donor",
                            "tx_idx0": int(tx0),
                            "genomic_1b": int(ginfo.genomic_1b_from_tx_idx0(int(tx0))),
                            "prob_ref": float(donor_ref[int(tx0)]),
                            "prob_alt": float(donor_alt[int(tx0)]),
                            "delta": float(donor_alt[int(tx0)] - donor_ref[int(tx0)]),
                        }
                    )

            top_calls = call_top_sites(
                gene_info=ginfo,
                seq_out=out_seq_ref,
                acceptor_probs=acceptor_ref,
                donor_probs=donor_ref,
                out_tx_start_idx0=out_tx_start,
                donor_label_mode=args.donor_label_mode,
                donor_kind_by_tx=donor_kind_by_tx,
                acceptor_kind_by_tx=acceptor_kind_by_tx,
                top_k=args.top_k,
                snap_k=args.snap_k,
            )

            res_gene: Dict[str, Any] = {
                "mode": "gene",
                "input_len": len(ref_in),
                "output_len": int(prob_ref.shape[1]),
                "out_tx_start_idx0": out_tx_start,
                "site_calls": {
                    "donor": [asdict(x) for x in top_calls["donor"]],
                    "acceptor": [asdict(x) for x in top_calls["acceptor"]],
                },
                "annot_sites": annot_sites,
            }

            if args.include_tracks:
                res_gene["tracks"] = {
                    "acceptor_ref": _round_floats(acceptor_ref),
                    "donor_ref": _round_floats(donor_ref),
                    "acceptor_alt": _round_floats(acceptor_alt),
                    "donor_alt": _round_floats(donor_alt),
                    "acceptor_delta": _round_floats(acceptor_alt - acceptor_ref),
                    "donor_delta": _round_floats(donor_alt - donor_ref),
                }

            results["gene"] = res_gene

        # -------------- mode: SNV-centered window --------------
        if args.mode in {"window", "both"}:
            ref_in, alt_in, ref_out, alt_out, out_tx_start = build_window_inputs(
                transcript_seq,
                input_len=input_len,
                core_len=core_len,
                flank_each=flank_each,
                var_tx_idx0=var_tx_idx0,
                ref_base=ref,
                alt_base=alt,
            )
            prob_ref = predict_probs_for_input(model, ref_in, device=device)  # [3, core_len]
            prob_alt = predict_probs_for_input(model, alt_in, device=device)

            acceptor_ref = prob_ref[1]
            donor_ref = prob_ref[2]
            acceptor_alt = prob_alt[1]
            donor_alt = prob_alt[2]

            # annotated sites that fall inside this core window
            core_start_tx = out_tx_start
            core_end_tx = out_tx_start + core_len

            annot_sites: List[Dict[str, Any]] = []
            for tx0, kind in sorted(acceptor_kind_by_tx.items(), key=lambda x: x[0]):
                if core_start_tx <= int(tx0) < core_end_tx:
                    j = int(tx0 - core_start_tx)
                    annot_sites.append(
                        {
                            "kind": kind,
                            "site_type": "acceptor",
                            "tx_idx0": int(tx0),
                            "idx0": int(j),
                            "genomic_1b": int(ginfo.genomic_1b_from_tx_idx0(int(tx0))),
                            "prob_ref": float(acceptor_ref[j]),
                            "prob_alt": float(acceptor_alt[j]),
                            "delta": float(acceptor_alt[j] - acceptor_ref[j]),
                        }
                    )
            for tx0, kind in sorted(donor_kind_by_tx.items(), key=lambda x: x[0]):
                if core_start_tx <= int(tx0) < core_end_tx:
                    j = int(tx0 - core_start_tx)
                    annot_sites.append(
                        {
                            "kind": kind,
                            "site_type": "donor",
                            "tx_idx0": int(tx0),
                            "idx0": int(j),
                            "genomic_1b": int(ginfo.genomic_1b_from_tx_idx0(int(tx0))),
                            "prob_ref": float(donor_ref[j]),
                            "prob_alt": float(donor_alt[j]),
                            "delta": float(donor_alt[j] - donor_ref[j]),
                        }
                    )

            top_calls = call_top_sites(
                gene_info=ginfo,
                seq_out=ref_out,
                acceptor_probs=acceptor_ref,
                donor_probs=donor_ref,
                out_tx_start_idx0=out_tx_start,
                donor_label_mode=args.donor_label_mode,
                donor_kind_by_tx=donor_kind_by_tx,
                acceptor_kind_by_tx=acceptor_kind_by_tx,
                top_k=args.top_k,
                snap_k=args.snap_k,
            )

            res_win: Dict[str, Any] = {
                "mode": "window",
                "input_len": len(ref_in),
                "output_len": int(prob_ref.shape[1]),
                "core_len": core_len,
                "flank_total": flank_total,
                "flank_each": flank_each,
                "input_center_idx0": input_len // 2,
                "core_center_idx0": core_len // 2,
                "out_tx_start_idx0": out_tx_start,
                "out_tx_end_idx0_excl": int(out_tx_start + core_len),
                "site_calls": {
                    "donor": [asdict(x) for x in top_calls["donor"]],
                    "acceptor": [asdict(x) for x in top_calls["acceptor"]],
                },
                "annot_sites": annot_sites,
            }

            if args.include_tracks:
                res_win["tracks"] = {
                    "acceptor_ref": _round_floats(acceptor_ref),
                    "donor_ref": _round_floats(donor_ref),
                    "acceptor_alt": _round_floats(acceptor_alt),
                    "donor_alt": _round_floats(donor_alt),
                    "acceptor_delta": _round_floats(acceptor_alt - acceptor_ref),
                    "donor_delta": _round_floats(donor_alt - donor_ref),
                }

            results["window"] = res_win

        vre["results"] = results
        report["variants"].append(vre)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote report -> {args.out}")


if __name__ == "__main__":
    main()
