from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..mission6.annotation import RefAnnotation
from ..mission6.backend_client import BackendClient
from ..mission6.genome import ReferenceGenome
from ..mission6.model import load_model

from .constants import CANONICAL_ACCEPTOR_MOTIF, CANONICAL_DONOR_MOTIFS
from .inference import InferenceConfig, encode_sequences, predict_probs_center_crop


@dataclass(frozen=True)
class CanonicalSite:
    kind: str
    site_type: str  # 'acceptor' | 'donor'
    exon_number: int
    pos_gene0: int


def _is_404(e: Exception) -> bool:
    s = str(e)
    return "status=404" in s or " 404 " in s or "404 Not Found" in s


def _pad_or_append(seq_parts: List[str], n: int) -> None:
    if n <= 0:
        return
    seq_parts.append("N" * int(n))


def assemble_gene_sequence_from_regions(
    regions: List[Dict[str, Any]],
    *,
    gene_length: int,
    allow_gap_pad: bool = True,
) -> str:
    """Assemble a gene0 sequence from DB regions (ordered by gene_start_idx).

    This treats DB gene_start_idx/gene_end_idx as the canonical coordinate frame.
    If some parts of the transcript are not stored in the region table, we can:
      - pad missing segments with 'N' (allow_gap_pad=True; recommended for robustness)
      - raise error (allow_gap_pad=False)
    """
    if gene_length <= 0:
        raise ValueError(f"gene_length must be > 0, got {gene_length}")
    if not regions:
        return "N" * gene_length

    regions_sorted = sorted(regions, key=lambda r: int(r["gene_start_idx"]))

    seq_parts: List[str] = []
    prev_end: Optional[int] = None

    for r in regions_sorted:
        start = int(r["gene_start_idx"])
        end = int(r["gene_end_idx"])
        if end < start:
            raise ValueError(f"Invalid region range: start={start}, end={end}")

        seq = str(r.get("sequence") or "").upper()
        expected_len = end - start + 1
        if len(seq) != expected_len:
            raise ValueError(
                f"Region length mismatch: region_id={r.get('region_id')} "
                f"len(sequence)={len(seq)} expected={expected_len} (start={start}, end={end})"
            )

        if prev_end is None:
            # prefix padding if the first region doesn't start at 0
            if start > 0:
                if allow_gap_pad:
                    _pad_or_append(seq_parts, start)
                else:
                    raise ValueError(f"First region does not start at 0 (start={start})")
        else:
            # handle gaps
            if start != prev_end + 1:
                gap = start - (prev_end + 1)
                if gap < 0:
                    raise ValueError(f"Overlapping regions: prev_end={prev_end}, next_start={start}")
                if allow_gap_pad:
                    _pad_or_append(seq_parts, gap)
                else:
                    raise ValueError(f"Non-contiguous regions: prev_end={prev_end}, next_start={start}")

        seq_parts.append(seq)
        prev_end = end

    assembled = "".join(seq_parts)

    # suffix padding
    if len(assembled) < gene_length:
        _pad_or_append(seq_parts, gene_length - len(assembled))
        assembled = "".join(seq_parts)

    if len(assembled) != gene_length:
        raise ValueError(f"Assembled gene_seq length mismatch: got {len(assembled)} expected {gene_length}")

    return assembled


def canonical_sites_from_exons(exons: List[Dict[str, Any]], *, exon_count: int) -> List[CanonicalSite]:
    """Return canonical splice sites derived STRICTLY from DB exon boundaries.

    Label convention (same as your Mission6 / Week10 label creation):
      - acceptor label = exon start index (exonN start)
      - donor label    = exon end index   (exonN end)

    Exclusions (transcript boundary is not labeled as splice site):
      - exon1 acceptor
      - exon{exon_count} donor
    """
    ex_by_n = {int(e["region_number"]): e for e in exons}

    sites: List[CanonicalSite] = []

    for n in range(1, exon_count + 1):
        exon = ex_by_n.get(n)
        if not exon:
            raise ValueError(f"Missing exon region for exon_number={n}")

        start = int(exon["gene_start_idx"])
        end = int(exon["gene_end_idx"])

        if n >= 2:
            sites.append(CanonicalSite(kind=f"exon{n}_acceptor", site_type="acceptor", exon_number=n, pos_gene0=start))
        if n <= exon_count - 1:
            sites.append(CanonicalSite(kind=f"exon{n}_donor", site_type="donor", exon_number=n, pos_gene0=end))

    # deterministic ordering:
    #   exon1_donor, exon2_acceptor, exon2_donor, exon3_acceptor, ...
    def _sort_key(s: CanonicalSite) -> Tuple[int, int]:
        # within exon: acceptor (start) first, donor (end) second
        t = 0 if s.site_type == "acceptor" else 1
        return (s.exon_number, t)

    return sorted(sites, key=_sort_key)


def motif_for_site(gene_seq: str, site: CanonicalSite) -> Optional[str]:
    """Return the canonical di-nucleotide motif around the labeled nucleotide.

    Convention (your "엄밀히 고려해야 할 부분"을 반영):
      - acceptor label at exon start pos => intron ends at pos-1
        => motif uses the last 2 nt of intron: gene_seq[pos-2:pos] should be 'AG'
        => actual cut happens between (pos-1) and (pos)

      - donor label at exon end pos => intron starts at pos+1
        => motif uses the first 2 nt of intron: gene_seq[pos+1:pos+3] should be 'GT' (or 'GC')
        => actual cut happens between (pos) and (pos+1)
    """
    pos = int(site.pos_gene0)
    if site.site_type == "acceptor":
        a = pos - 2
        b = pos
        if a < 0 or b > len(gene_seq):
            return None
        return gene_seq[a:b].upper()

    a = pos + 1
    b = pos + 3
    if a < 0 or b > len(gene_seq):
        return None
    return gene_seq[a:b].upper()


def motif_ok(site: CanonicalSite, motif: Optional[str]) -> Optional[bool]:
    if motif is None:
        return None
    if site.site_type == "acceptor":
        return motif == CANONICAL_ACCEPTOR_MOTIF
    return motif in CANONICAL_DONOR_MOTIFS


def rank_array_desc(probs_1d: np.ndarray) -> np.ndarray:
    """Return rank per position (1=highest)."""
    order = np.argsort(-probs_1d, kind="mergesort")
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, len(probs_1d) + 1)
    return ranks


def _compare_sequences_ignore_n(db_seq: str, ref_seq: str, *, max_show: int = 20) -> Dict[str, Any]:
    """Compare DB vs reference transcript sequence, ignoring DB positions that are 'N'.

    This is important because DB may intentionally not store transcript prefix/suffix,
    and we pad those gaps with 'N' (mask).
    """
    if len(db_seq) != len(ref_seq):
        return {
            "ok": False,
            "reason": "length_mismatch",
            "len_db": len(db_seq),
            "len_ref": len(ref_seq),
        }

    mismatches: List[Dict[str, Any]] = []
    mismatch_count = 0
    covered = 0
    for i, (b_db, b_ref) in enumerate(zip(db_seq, ref_seq)):
        b_db = b_db.upper()
        b_ref = b_ref.upper()
        if b_db in "ACGT":
            covered += 1
            if b_db != b_ref:
                mismatch_count += 1
                if len(mismatches) < max_show:
                    mismatches.append({"pos_gene0": i, "db": b_db, "ref": b_ref})
        else:
            # treat N / unknown as masked (do not count mismatch)
            pass

    return {
        "ok": mismatch_count == 0,
        "len": len(db_seq),
        "covered_bases": covered,
        "covered_rate": float(covered / max(1, len(db_seq))),
        "mismatch_count": mismatch_count,
        "mismatch_samples": mismatches,
    }


def _expected_exons_gene0_from_annotation(row: Any) -> Tuple[np.ndarray, np.ndarray]:
    """Return (exon_start_gene0, exon_end_gene0) in transcript order."""
    tx_start = int(row["TX_START"])
    tx_end = int(row["TX_END"])
    strand = str(row["STRAND"])

    starts = np.asarray(row["EXON_START"], dtype=int)
    ends = np.asarray(row["EXON_END"], dtype=int)
    if starts.size == 0:
        return np.asarray([], dtype=int), np.asarray([], dtype=int)

    # transcript order: + ascending, - descending (by genomic coordinate)
    order = np.argsort(starts)
    if strand == "-":
        order = order[::-1]
    starts = starts[order]
    ends = ends[order]

    if strand == "+":
        s_gene0 = starts - tx_start
        e_gene0 = ends - tx_start
    else:
        # gene0=0 at genomic TX_END
        s_gene0 = tx_end - ends
        e_gene0 = tx_end - starts

    return s_gene0.astype(int), e_gene0.astype(int)


def _exon_boundary_check(db_exons: List[Dict[str, Any]], row: Any) -> Dict[str, Any]:
    """Compare DB exon boundaries (gene0) vs annotation-derived exon boundaries (gene0)."""
    exp_s, exp_e = _expected_exons_gene0_from_annotation(row)
    if exp_s.size == 0:
        return {"ok": False, "reason": "annotation_has_no_exons"}

    db_by_n = {int(e["region_number"]): e for e in db_exons}
    exon_count_db = len(db_by_n)
    exon_count_ann = int(exp_s.size)

    mismatches: List[Dict[str, Any]] = []
    n_common = min(exon_count_db, exon_count_ann)

    for n in range(1, n_common + 1):
        e = db_by_n.get(n)
        if not e:
            mismatches.append({"exon_number": n, "reason": "missing_in_db"})
            continue
        s_db = int(e["gene_start_idx"])
        e_db = int(e["gene_end_idx"])
        s_exp = int(exp_s[n - 1])
        e_exp = int(exp_e[n - 1])
        if s_db != s_exp or e_db != e_exp:
            mismatches.append(
                {
                    "exon_number": n,
                    "db": {"start_gene0": s_db, "end_gene0": e_db},
                    "expected": {"start_gene0": s_exp, "end_gene0": e_exp},
                }
            )

    ok = (len(mismatches) == 0) and (exon_count_db == exon_count_ann)
    return {
        "ok": ok,
        "exon_count_db": exon_count_db,
        "exon_count_annotation": exon_count_ann,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "note": "Annotation exons are ordered in transcript order (+ asc, - desc).",
    }


def _orf_sanity_from_exons(exons: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Very lightweight ORF sanity check on spliced (exon-only) sequence.

    - Find first 'ATG'
    - Find first in-frame stop among {'TAA','TAG','TGA'}
    """
    ex_by_n = {int(e["region_number"]): e for e in exons}
    if not ex_by_n:
        return {"ok": False, "reason": "no_exons"}

    seq = "".join(str(ex_by_n[n].get("sequence") or "").upper() for n in sorted(ex_by_n))
    if not seq:
        return {"ok": False, "reason": "empty_exon_sequence"}

    start_idx = seq.find("ATG")
    if start_idx < 0:
        return {"ok": False, "reason": "no_start_codon_ATG"}

    stop_codons = {"TAA", "TAG", "TGA"}
    stop_idx = None
    stop_codon = None
    for i in range(start_idx + 3, len(seq) - 2, 3):
        cod = seq[i : i + 3]
        if cod in stop_codons:
            stop_idx = i
            stop_codon = cod
            break

    if stop_idx is None:
        return {
            "ok": False,
            "reason": "no_in_frame_stop_codon",
            "start_idx0": start_idx,
            "mRNA_len": len(seq),
        }

    orf_len_nt = (stop_idx + 3) - start_idx
    orf_len_aa = orf_len_nt // 3
    return {
        "ok": True,
        "start_idx0": start_idx,
        "stop_idx0": stop_idx,
        "stop_codon": stop_codon,
        "orf_len_nt": int(orf_len_nt),
        "orf_len_aa": int(orf_len_aa),
        "mRNA_len": int(len(seq)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "STEP3 canonical validation: "
            "(1) DB region sequences vs annotation+FASTA, "
            "(2) canonical splice-site probabilities at ALL DB canonical sites across whole gene, "
            "(3) (optional) ORF sanity check on exon-only sequence."
        )
    )
    ap.add_argument("--backend-url", required=True, help="FastAPI base URL (e.g. http://localhost:8000)")
    ap.add_argument("--model", required=True, help="trained model checkpoint (.pt)")
    ap.add_argument("--out", default="report_canonical_sites.json")

    # For sequence validation (recommended)
    ap.add_argument("--annotation", required=True, help="refannotation_with_canonical.tsv")
    ap.add_argument("--fasta", required=True, help="GRCh38.primary_assembly.genome.fa")

    ap.add_argument("--disease-id", default=None, help="If set, evaluate only this disease_id")

    ap.add_argument("--flank", type=int, default=10000, help="Total flank length used in training (default 10000 => pad 5000 each side)")
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--device", default=None, help="cpu/cuda/mps")

    ap.add_argument("--strict-contiguous", action="store_true", help="Fail if DB regions have gaps (no N padding). Default is to pad gaps with N for robustness.")
    ap.add_argument("--orf-sanity", action="store_true", help="Check start/stop codon on exon-only (spliced) sequence")

    args = ap.parse_args()

    flank_total = int(args.flank)
    if flank_total <= 0 or (flank_total % 2) != 0:
        raise SystemExit("--flank must be a positive EVEN integer (e.g. 10000)")
    pad_each = flank_total // 2

    ann = RefAnnotation(args.annotation)
    genome = ReferenceGenome(args.fasta)

    bc = BackendClient(args.backend_url)
    model = load_model(args.model)
    cfg = InferenceConfig(batch_size=int(args.batch_size), device=args.device)

    # disease list
    if args.disease_id:
        disease_ids = [str(args.disease_id)]
        disease_meta_by_id: Dict[str, Dict[str, Any]] = {}
    else:
        ds = bc.list_diseases()
        disease_ids = [str(d["disease_id"]) for d in ds if d.get("disease_id")]
        disease_meta_by_id = {str(d.get("disease_id")): d for d in ds if d.get("disease_id")}

    results: List[Dict[str, Any]] = []

    for did in disease_ids:
        payload = bc.get_step2_payload(did, include_sequence=False)
        gene = payload.get("gene") or {}
        disease = payload.get("disease") or {}
        snv = payload.get("splice_altering_snv") or {}

        gene_id = str(gene.get("gene_id") or disease.get("gene_id") or "")
        if not gene_id:
            raise ValueError(f"Missing gene_id in payload for disease_id={did}")

        exon_count = int(gene.get("exon_count"))
        gene_length = int(gene.get("length"))
        strand_db = str(gene.get("strand"))

        # -------------------------
        # Fetch regions from backend
        # -------------------------
        exons: List[Dict[str, Any]] = []
        introns: List[Dict[str, Any]] = []

        for n in range(1, exon_count + 1):
            reg = bc.get_region(did, "exon", n, include_sequence=True)
            exons.append(reg["region"] if "region" in reg else reg)

        # introns are typically 1..exon_count-1
        for n in range(1, exon_count):
            try:
                reg = bc.get_region(did, "intron", n, include_sequence=True)
            except Exception as e:
                if _is_404(e):
                    continue
                raise
            introns.append(reg["region"] if "region" in reg else reg)

        regions_all = exons + introns
        gene_seq_db = assemble_gene_sequence_from_regions(
            regions_all,
            gene_length=gene_length,
            allow_gap_pad=not bool(args.strict_contiguous),
        )

        # -------------------------
        # Reference sequence (annotation + FASTA)
        # -------------------------
        row = ann.get_gene_row(gene_id)
        chrom = str(row["CHROM"])
        strand_ann = str(row["STRAND"])
        tx_start_1b = int(row["TX_START"])
        tx_end_1b = int(row["TX_END"])

        # fetch transcript (TX_START..TX_END inclusive) => 0-based half-open
        ref_seq = genome.fetch_seq(chrom, tx_start_1b - 1, tx_end_1b, strand=strand_ann).upper()

        seq_check = _compare_sequences_ignore_n(gene_seq_db, ref_seq, max_show=20)
        exon_check = _exon_boundary_check(exons, row)

        # -------------------------
        # Whole-gene inference
        # -------------------------
        seq_in = ("N" * pad_each) + gene_seq_db + ("N" * pad_each)
        X = encode_sequences([seq_in])

        # We want probabilities for the central gene_length positions
        prob = predict_probs_center_crop(
            model,
            X,
            in_length=len(seq_in),
            out_length=len(gene_seq_db),
            cfg=cfg,
        )[0]  # (3,L)

        acc = prob[1]
        don = prob[2]
        rank_acc = rank_array_desc(acc)
        rank_don = rank_array_desc(don)
        L = len(gene_seq_db)

        sites = canonical_sites_from_exons(exons, exon_count=exon_count)

        rows_sites: List[Dict[str, Any]] = []
        for s in sites:
            pos = int(s.pos_gene0)
            if pos < 0 or pos >= L:
                continue

            m_db = motif_for_site(gene_seq_db, s)
            ok_db = motif_ok(s, m_db)

            # genomic coordinate for convenience (1-based)
            if strand_ann == "+":
                genomic_1b = tx_start_1b + pos
            else:
                genomic_1b = tx_end_1b - pos

            if s.site_type == "acceptor":
                p_site = float(acc[pos])
                rk = int(rank_acc[pos])
                pct = float(100.0 * (1.0 - (rk - 1) / max(1, L - 1)))
                cut = {"left_gene0": pos - 1, "right_gene0": pos}
            else:
                p_site = float(don[pos])
                rk = int(rank_don[pos])
                pct = float(100.0 * (1.0 - (rk - 1) / max(1, L - 1)))
                cut = {"left_gene0": pos, "right_gene0": pos + 1}

            rows_sites.append(
                {
                    "kind": s.kind,
                    "site_type": s.site_type,
                    "exon_number": s.exon_number,
                    "pos_gene0": pos,
                    "genomic_1b": int(genomic_1b),
                    "junction_cut_gene0": cut,
                    "motif_db": m_db,
                    "motif_ok_db": ok_db,
                    "prob": p_site,
                    "rank": rk,
                    "percentile": pct,
                }
            )

        # keep stable exon-order
        rows_sites = sorted(rows_sites, key=lambda r: (int(r["exon_number"]), 0 if r["site_type"] == "acceptor" else 1))

        def _summary(rows: List[Dict[str, Any]], site_type: str) -> Dict[str, Any]:
            xs = [r for r in rows if r["site_type"] == site_type]
            if not xs:
                return {"n": 0}
            probs = np.array([float(r["prob"]) for r in xs], dtype=float)
            ranks = np.array([int(r["rank"]) for r in xs], dtype=int)
            motif_ok_vals = [r.get("motif_ok_db") for r in xs if r.get("motif_ok_db") is not None]
            motif_ok_rate = None
            if motif_ok_vals:
                motif_ok_rate = float(np.mean(np.array(motif_ok_vals, dtype=float)))
            return {
                "n": int(len(xs)),
                "prob_min": float(probs.min()),
                "prob_median": float(np.median(probs)),
                "prob_max": float(probs.max()),
                "rank_best": int(ranks.min()),
                "rank_median": int(np.median(ranks)),
                "motif_ok_rate": motif_ok_rate,
            }

        out_item: Dict[str, Any] = {
            "disease_id": did,
            "disease_name": disease.get("disease_name") or disease_meta_by_id.get(did, {}).get("disease_name"),
            "gene_id": gene_id,
            "strand_db": strand_db,
            "strand_annotation": strand_ann,
            "chrom": chrom,
            "tx_start_1b": tx_start_1b,
            "tx_end_1b": tx_end_1b,
            "gene_length": gene_length,
            "exon_count": exon_count,
            "snv": {
                "pos_gene0": int(snv.get("pos_gene0")) if snv.get("pos_gene0") is not None else None,
                "ref": snv.get("ref"),
                "alt": snv.get("alt"),
            },
            "sequence_check": seq_check,
            "exon_boundary_check": exon_check,
            "model": {
                "checkpoint": args.model,
                "flank_total": flank_total,
                "pad_each": pad_each,
                "input_len": int(len(seq_in)),
                "output_len": int(len(gene_seq_db)),
            },
            "canonical_sites": rows_sites,
            "summary": {
                "acceptor": _summary(rows_sites, "acceptor"),
                "donor": _summary(rows_sites, "donor"),
            },
        }

        if args.orf_sanity:
            out_item["orf_sanity_exon_only"] = _orf_sanity_from_exons(exons)

        results.append(out_item)

    out_obj = {
        "meta": {
            "backend_url": args.backend_url,
            "model": args.model,
            "annotation": args.annotation,
            "fasta": args.fasta,
            "flank_total": flank_total,
            "pad_each": pad_each,
            "device": args.device,
            "batch_size": int(args.batch_size),
            "allow_gap_pad": not bool(args.strict_contiguous),
            "orf_sanity": bool(args.orf_sanity),
        },
        "results": results,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote report -> {args.out}")


if __name__ == "__main__":
    main()
