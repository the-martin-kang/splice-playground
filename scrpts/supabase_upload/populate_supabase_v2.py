#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Populate Supabase (Postgres) for splice-playground (new DDL) using:

  1) refannotation_with_canonical.tsv  (TSV derived from GTF)
  2) GRCh38.primary_assembly.genome.fa (FASTA; needs .fai or pyfaidx will build)
  3) selected_gene.tsv                (your curated "case list" with disease_name + SNV)

Populates (ALL tables except the 3 runtime tables below):
  - public.gene
  - public.disease
  - public.region
  - public.splice_altering_snv
  - public.editing_target_window
  - public.baseline_result   (step3 only; naive canonical = all exons included)

Does NOT populate:
  - public.user_state
  - public.user_state_result
  - public.structure_job

Requirements:
  pip install pandas pyfaidx supabase

Env:
  export SUPABASE_URL="https://xxxx.supabase.co"
  export SUPABASE_SERVICE_KEY="service_role_key"

Example:
  python populate_supabase_v2.py \
    --ref refannotation_with_canonical.tsv \
    --fasta GRCh38.primary_assembly.genome.fa \
    --selected selected_gene.tsv \
    --source-version gencode.v46 \
    --baseline-model-version canonical_v1
"""

from __future__ import annotations

import argparse
import os
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
from pyfaidx import Fasta
from supabase import create_client


DNA_COMP = str.maketrans("ACGTNacgtn", "TGCANtgcan")

# A fixed namespace UUID for deterministic IDs (idempotent re-runs)
ETL_NAMESPACE = uuid.UUID("1b8c2a7e-4b5a-4b8b-b59f-2a8e8e9c3b4f")


# -----------------------------
# Small utilities
# -----------------------------
def revcomp(seq: str) -> str:
    return seq.translate(DNA_COMP)[::-1]


def complement_base(base: str) -> str:
    b = (base or "").strip()
    if len(b) != 1:
        raise ValueError(f"Expected single base, got: {base!r}")
    return b.translate(DNA_COMP).upper()


def parse_coord_list(s: Any) -> List[int]:
    if pd.isna(s):
        return []
    parts = [p.strip() for p in str(s).split(",") if p.strip() != "" and p.strip().lower() != "nan"]
    return [int(p) for p in parts]


def parse_int_list(s: Any) -> List[int]:
    if pd.isna(s):
        return []
    parts = [p.strip() for p in str(s).split(",") if p.strip() != "" and p.strip().lower() != "nan"]
    return [int(p) for p in parts]


def pick_col(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def stable_uuid(name: str) -> str:
    """Return deterministic UUID string for a given name."""
    return str(uuid.uuid5(ETL_NAMESPACE, name))


def normalize_chrom(chrom: str, fasta_has_chr_prefix: bool) -> str:
    chrom = str(chrom).strip()
    has_chr = chrom.lower().startswith("chr")
    if fasta_has_chr_prefix and not has_chr:
        return "chr" + chrom
    if (not fasta_has_chr_prefix) and has_chr:
        return chrom[3:]
    return chrom


def fasta_slice_1based_inclusive(fa: Fasta, chrom: str, start_1: int, end_1: int) -> str:
    """Return uppercase DNA sequence from FASTA using 1-based inclusive coordinates."""
    return str(fa[chrom][start_1 - 1 : end_1]).upper()


def gene_pos_to_gene0(strand: str, tx_start_1: int, tx_end_1: int, pos_chr1: int) -> int:
    """gene0: 0-based index in transcript direction (5'->3') relative to tx_start/tx_end."""
    if strand == "+":
        return pos_chr1 - tx_start_1
    return tx_end_1 - pos_chr1


def region_chr_to_gene0_bounds(
    strand: str, tx_start_1: int, tx_end_1: int, start_chr1: int, end_chr1: int
) -> Tuple[int, int]:
    """Return (gene_start_idx, gene_end_idx) inclusive in gene0 coordinates."""
    if strand == "+":
        return start_chr1 - tx_start_1, end_chr1 - tx_start_1
    return tx_end_1 - end_chr1, tx_end_1 - start_chr1


def chunked(seq: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def batch_upsert(sb, table: str, rows: List[Dict[str, Any]], batch_size: int = 50) -> None:
    """Upsert rows in batches (keeps request payload manageable)."""
    for chunk in chunked(rows, batch_size):
        if not chunk:
            continue
        sb.table(table).upsert(chunk).execute()


# -----------------------------
# Canonical exon selection
# -----------------------------
def select_canonical_exons(
    exon_starts_all: List[int],
    exon_ends_all: List[int],
    canonical_exon_numbers: List[int],
) -> List[Tuple[int, int]]:
    """
    exon_starts_all / exon_ends_all:
      full exon coordinate list (1-based inclusive) from TSV.
    canonical_exon_numbers:
      1-based indices selecting which entries correspond to canonical transcript.
      If empty -> use all.
    """
    if len(exon_starts_all) != len(exon_ends_all):
        raise ValueError("EXON_START/EXON_END length mismatch")

    if canonical_exon_numbers:
        idxs = []
        for n in canonical_exon_numbers:
            if 1 <= n <= len(exon_starts_all):
                idxs.append(n - 1)
            else:
                raise ValueError(f"canonical_exon_numbers contains out-of-range index: {n}")
        exons = [(int(exon_starts_all[i]), int(exon_ends_all[i])) for i in idxs]
    else:
        exons = list(zip(exon_starts_all, exon_ends_all))

    # de-dup while preserving order (some rows have duplicates)
    seen = set()
    uniq: List[Tuple[int, int]] = []
    for s, e in exons:
        key = (int(s), int(e))
        if key not in seen:
            seen.add(key)
            uniq.append(key)
    return uniq


# -----------------------------
# Window picking (±2 regions)
# -----------------------------
def pick_5_region_window(center_idx: int, total: int) -> Tuple[int, int]:
    """
    Return (start_idx, end_idx) inclusive for a 5-region window.
    If total < 5 -> returns full span.
    """
    if total <= 0:
        raise ValueError("total must be > 0")
    if total <= 5:
        return (0, total - 1)

    window = 5
    half = 2
    start = center_idx - half
    end = start + window - 1

    if start < 0:
        start = 0
        end = window - 1
    if end >= total:
        end = total - 1
        start = end - (window - 1)
    start = max(0, start)
    end = min(total - 1, end)
    return (start, end)


# -----------------------------
# Main ETL
# -----------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="refannotation_with_canonical.tsv")
    ap.add_argument("--fasta", required=True, help="GRCh38.primary_assembly.genome.fa")
    ap.add_argument("--selected", required=True, help="selected_gene.tsv")

    ap.add_argument("--source-version", default="gencode.v46")
    ap.add_argument("--baseline-model-version", default="canonical_v1", help="baseline_result.model_version for step3")
    ap.add_argument("--batch-size", type=int, default=50)

    ap.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL", ""))
    ap.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SERVICE_KEY", ""))
    ap.add_argument("--dry-run", action="store_true", help="Parse everything but do not write to Supabase.")
    args = ap.parse_args()

    if not args.supabase_url or not args.supabase_key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY (service role key) or pass via args.")

    # --- Load refannotation ---
    ref_df = pd.read_csv(args.ref, sep="\t")
    required_ref_cols = [
        "NAME",
        "CHROM",
        "STRAND",
        "TX_START",
        "TX_END",
        "EXON_START",
        "EXON_END",
        "canonical_exon_numbers",
        "canonical_transcript_id",
        "canonical_source",
    ]
    missing = [c for c in required_ref_cols if c not in ref_df.columns]
    if missing:
        raise SystemExit(f"refannotation_with_canonical.tsv missing columns: {missing}")

    ref_df["NAME"] = ref_df["NAME"].astype(str).str.strip()
    ref_by_name: Dict[str, Dict[str, Any]] = {r["NAME"]: r.to_dict() for _, r in ref_df.iterrows()}

    # --- Load selected cases ---
    sel_df = pd.read_csv(args.selected, sep="\t")

    sel_gene_col = pick_col(sel_df, ["gene", "NAME", "Gene", "gene_symbol"])
    sel_chrom_col = pick_col(sel_df, ["chrom", "CHROM", "chr"])
    sel_pos_col = pick_col(sel_df, ["pos", "POS", "position"])
    sel_ref_col = pick_col(sel_df, ["ref", "REF"])
    sel_alt_col = pick_col(sel_df, ["alt", "ALT"])
    sel_dname_col = pick_col(sel_df, ["disease_name"])
    sel_strand_col = pick_col(sel_df, ["strand", "STRAND"])

    if None in [sel_gene_col, sel_chrom_col, sel_pos_col, sel_ref_col, sel_alt_col, sel_dname_col]:
        raise SystemExit(
            "selected TSV must contain at least: gene, chrom, pos, ref, alt, disease_name.\n"
            f"Found columns: {list(sel_df.columns)}"
        )

    sel_df[sel_gene_col] = sel_df[sel_gene_col].astype(str).str.strip()
    sel_df[sel_dname_col] = sel_df[sel_dname_col].astype(str).str.strip()

    genes_to_upload = sorted(set(sel_df[sel_gene_col].tolist()))
    missing_genes = [g for g in genes_to_upload if g not in ref_by_name]
    if missing_genes:
        raise SystemExit(f"Genes in selected file not found in refannotation_with_canonical.tsv: {missing_genes}")

    # --- FASTA ---
    fa = Fasta(args.fasta)
    fasta_has_chr = any(str(k).startswith("chr") for k in list(fa.keys())[:50])

    # --- Supabase ---
    sb = create_client(args.supabase_url, args.supabase_key)

    # =========================
    # 1) gene + region (+ baseline_result step3)
    # =========================
    gene_rows: List[Dict[str, Any]] = []
    region_rows: List[Dict[str, Any]] = []
    baseline_rows: List[Dict[str, Any]] = []

    # For window computation later
    region_order_by_gene: Dict[str, List[Dict[str, Any]]] = {}

    for gene_name in genes_to_upload:
        r = ref_by_name[gene_name]

        chrom = normalize_chrom(r["CHROM"], fasta_has_chr)
        strand = str(r["STRAND"]).strip()
        if strand not in {"+", "-"}:
            raise SystemExit(f"Invalid strand for {gene_name}: {strand}")

        tx_start = int(r["TX_START"])
        tx_end = int(r["TX_END"])
        if tx_end < tx_start:
            raise SystemExit(f"TX_END < TX_START for {gene_name}: {tx_start}, {tx_end}")

        exon_starts_all = parse_coord_list(r["EXON_START"])
        exon_ends_all = parse_coord_list(r["EXON_END"])
        canonical_numbers = parse_int_list(r.get("canonical_exon_numbers"))

        exons = select_canonical_exons(exon_starts_all, exon_ends_all, canonical_numbers)

        # sort exons into transcript order
        exons.sort(key=lambda x: x[0], reverse=(strand == "-"))

        exon_count = len(exons)
        if exon_count <= 0:
            raise SystemExit(f"No exons found for {gene_name} after canonical selection")

        gene_id = gene_name
        gene_len = tx_end - tx_start + 1

        canonical_transcript_id = (
            str(r["canonical_transcript_id"]) if pd.notna(r.get("canonical_transcript_id")) else None
        )
        canonical_source = str(r["canonical_source"]) if pd.notna(r.get("canonical_source")) else None

        gene_rows.append(
            {
                "gene_id": gene_id,
                "gene_symbol": gene_name,
                "chromosome": chrom,
                "strand": strand,
                "length": int(gene_len),
                "exon_count": int(exon_count),
                "canonical_transcript_id": canonical_transcript_id,
                "canonical_source": canonical_source,
                "source_version": args.source_version,
            }
        )

        # Build regions in strict order: exon1, intron1, exon2, ...
        ordered_regions_for_window: List[Dict[str, Any]] = []

        # Exons
        exon_regions: List[Dict[str, Any]] = []
        for i, (s, e) in enumerate(exons, start=1):
            s = int(s)
            e = int(e)
            if e < s:
                raise SystemExit(f"Exon end < start for {gene_name} exon{i}: {s},{e}")

            seq = fasta_slice_1based_inclusive(fa, chrom, s, e)
            if strand == "-":
                seq = revcomp(seq)

            gs, ge = region_chr_to_gene0_bounds(strand, tx_start, tx_end, s, e)
            length = e - s + 1
            if (ge - gs + 1) != length:
                raise SystemExit(f"Gene0 bounds length mismatch for {gene_name} exon{i}")

            row = {
                "region_id": f"{gene_id}_exon_{i}",
                "gene_id": gene_id,
                "region_type": "exon",
                "region_number": int(i),
                "gene_start_idx": int(gs),
                "gene_end_idx": int(ge),
                "length": int(length),
                "sequence": seq,
                "cds_start_offset": None,
                "cds_end_offset": None,
            }
            exon_regions.append(row)

        # Introns between exons (in transcript order)
        intron_regions: List[Dict[str, Any]] = []
        for i in range(1, exon_count):  # intron i between exon i and exon i+1
            s1, e1 = exons[i - 1]
            s2, e2 = exons[i]

            intron_start = min(int(e1), int(e2)) + 1
            intron_end = max(int(s1), int(s2)) - 1
            if intron_end < intron_start:
                # adjacent exons
                continue

            seq = fasta_slice_1based_inclusive(fa, chrom, intron_start, intron_end)
            if strand == "-":
                seq = revcomp(seq)

            gs, ge = region_chr_to_gene0_bounds(strand, tx_start, tx_end, intron_start, intron_end)
            length = intron_end - intron_start + 1
            if (ge - gs + 1) != length:
                raise SystemExit(f"Gene0 bounds length mismatch for {gene_name} intron{i}")

            row = {
                "region_id": f"{gene_id}_intron_{i}",
                "gene_id": gene_id,
                "region_type": "intron",
                "region_number": int(i),
                "gene_start_idx": int(gs),
                "gene_end_idx": int(ge),
                "length": int(length),
                "sequence": seq,
                "cds_start_offset": None,
                "cds_end_offset": None,
            }
            intron_regions.append(row)

        # Merge exon/intron into alternating transcript order list for UI/window picking
        intron_by_num = {r["region_number"]: r for r in intron_regions}
        for i in range(1, exon_count + 1):
            ordered_regions_for_window.append(exon_regions[i - 1])
            if i < exon_count and i in intron_by_num:
                ordered_regions_for_window.append(intron_by_num[i])

        region_order_by_gene[gene_id] = ordered_regions_for_window

        # Append to global region rows
        region_rows.extend(exon_regions)
        region_rows.extend(intron_regions)

        # baseline_result (step3 naive canonical)
        baseline_rows.append(
            {
                "gene_id": gene_id,
                "step": "step3",
                "model_version": args.baseline_model_version,
                "result_payload": {
                    "included_exons": list(range(1, exon_count + 1)),
                    "excluded_exons": [],
                    "canonical_transcript_id": canonical_transcript_id,
                    "canonical_source": canonical_source,
                    "note": "baseline step3 derived from canonical exon list (no splicing prediction)",
                },
            }
        )

    print(f"[INFO] genes: {len(gene_rows)}")
    print(f"[INFO] regions: {len(region_rows)}")
    print(f"[INFO] baseline_result(step3): {len(baseline_rows)}")

    if not args.dry_run:
        batch_upsert(sb, "gene", gene_rows, batch_size=args.batch_size)

        # Regions can be large; consider smaller batch size if you hit request size limits
        batch_upsert(sb, "region", region_rows, batch_size=max(5, min(args.batch_size, 25)))

        batch_upsert(sb, "baseline_result", baseline_rows, batch_size=args.batch_size)

    # =========================
    # 2) disease + splice_altering_snv
    # =========================
    disease_rows: Dict[str, Dict[str, Any]] = {}
    snv_rows: List[Dict[str, Any]] = []

    for _, v in sel_df.iterrows():
        gene_name = str(v[sel_gene_col]).strip()
        r = ref_by_name[gene_name]

        chrom_ref = normalize_chrom(v[sel_chrom_col], fasta_has_chr)
        chrom_from_ref = normalize_chrom(r["CHROM"], fasta_has_chr)

        if chrom_ref != chrom_from_ref:
            raise SystemExit(f"Chrom mismatch for {gene_name}: selected={chrom_ref}, ref={chrom_from_ref}")

        strand_ref = str(r["STRAND"]).strip()
        if sel_strand_col is not None and pd.notna(v[sel_strand_col]):
            strand_sel = str(v[sel_strand_col]).strip()
            if strand_sel in {"+", "-"} and strand_sel != strand_ref:
                raise SystemExit(f"Strand mismatch for {gene_name}: selected={strand_sel}, ref={strand_ref}")

        tx_start = int(r["TX_START"])
        tx_end = int(r["TX_END"])

        pos_chr1 = int(v[sel_pos_col])  # 1-based chromosome coordinate
        ref_in = str(v[sel_ref_col]).strip().upper()
        alt_in = str(v[sel_alt_col]).strip().upper()
        disease_name = str(v[sel_dname_col]).strip()

        if len(ref_in) != 1 or len(alt_in) != 1:
            raise SystemExit(f"Only SNV supported (single base). Got ref={ref_in}, alt={alt_in} for {gene_name}")

        # Validate REF against FASTA at genomic position (forward strand)
        fasta_ref = fasta_slice_1based_inclusive(fa, chrom_ref, pos_chr1, pos_chr1)
        genomic_ref = ref_in
        genomic_alt = alt_in

        if fasta_ref != genomic_ref:
            # If this is a '-' gene, user might have provided ref/alt in gene-orientation (revcomp).
            if strand_ref == "-" and fasta_ref == complement_base(genomic_ref):
                # Convert provided ref/alt to genomic for note, but keep gene-oriented as provided
                genomic_ref = fasta_ref
                genomic_alt = complement_base(alt_in)
                print(
                    f"[WARN] {gene_name}: input ref/alt looked gene-oriented for '-' strand; "
                    f"accepting by complementing. (FASTA={fasta_ref}, input_ref={ref_in})"
                )
            else:
                raise SystemExit(
                    f"REF mismatch for {gene_name} at {chrom_ref}:{pos_chr1}. FASTA={fasta_ref} != input_ref={ref_in}"
                )

        pos_gene0 = gene_pos_to_gene0(strand_ref, tx_start, tx_end, pos_chr1)
        gene_len = tx_end - tx_start + 1
        if pos_gene0 < 0 or pos_gene0 >= gene_len:
            raise SystemExit(
                f"pos_gene0 out of range for {gene_name}: pos_chr1={pos_chr1}, pos_gene0={pos_gene0}, gene_len={gene_len}"
            )

        # Store ref/alt in gene-orientation (matches region.sequence orientation)
        if strand_ref == "+":
            ref_gene = ref_in
            alt_gene = alt_in
        else:
            ref_gene = complement_base(ref_in)
            alt_gene = complement_base(alt_in)

        disease_id = f"{gene_name}_gene0_{pos_gene0}_{ref_gene}>{alt_gene}"

        # disease (dedup by id)
        if disease_id in disease_rows:
            # sanity check: same disease_id must mean same disease_name and gene
            prev = disease_rows[disease_id]
            if prev["disease_name"] != disease_name or prev["gene_id"] != gene_name:
                raise SystemExit(
                    f"Conflicting rows for disease_id={disease_id}: {prev} vs disease_name={disease_name}, gene={gene_name}"
                )
        else:
            disease_rows[disease_id] = {
                "disease_id": disease_id,
                "disease_name": disease_name,
                "description": None,
                "image_path": None,
                "gene_id": gene_name,
            }

        # splice_altering_snv
        snv_id = stable_uuid(f"snv:{disease_id}:{gene_name}:{pos_gene0}:{ref_gene}>{alt_gene}")
        snv_rows.append(
            {
                "snv_id": snv_id,
                "disease_id": disease_id,
                "gene_id": gene_name,
                "pos_gene0": int(pos_gene0),
                "ref": ref_gene,
                "alt": alt_gene,
                "is_representative": False,  # set after grouping
                "chromosome": chrom_ref,
                "pos_hg38_1": int(pos_chr1),
                "note": f"chrom={chrom_ref};pos1={pos_chr1};genomic_ref={genomic_ref};genomic_alt={genomic_alt}",
            }
        )

    # Choose representative SNV per disease (first row wins)
    rep_chosen: Dict[str, bool] = {}
    for row in snv_rows:
        did = row["disease_id"]
        if did not in rep_chosen:
            row["is_representative"] = True
            rep_chosen[did] = True

    print(f"[INFO] diseases: {len(disease_rows)}")
    print(f"[INFO] splice_altering_snv: {len(snv_rows)} (representative={sum(1 for r in snv_rows if r['is_representative'])})")

    if not args.dry_run:
        batch_upsert(sb, "disease", list(disease_rows.values()), batch_size=args.batch_size)
        batch_upsert(sb, "splice_altering_snv", snv_rows, batch_size=args.batch_size)

    # =========================
    # 3) editing_target_window (default 5-region window around representative SNV)
    # =========================
    window_rows: List[Dict[str, Any]] = []

    # Build a quick lookup for representative SNV per disease
    rep_snv_by_disease: Dict[str, Dict[str, Any]] = {}
    for row in snv_rows:
        if row["is_representative"]:
            rep_snv_by_disease[row["disease_id"]] = row

    for disease_id, snv in rep_snv_by_disease.items():
        gene_id = snv["gene_id"]
        pos_gene0 = int(snv["pos_gene0"])

        ordered = region_order_by_gene.get(gene_id)
        if not ordered:
            raise SystemExit(f"No regions found for gene {gene_id} (needed for window)")

        # find the region that contains the SNV
        center_idx = None
        for i, reg in enumerate(ordered):
            if int(reg["gene_start_idx"]) <= pos_gene0 <= int(reg["gene_end_idx"]):
                center_idx = i
                break
        if center_idx is None:
            # This can happen if tx_start/tx_end cover more than exon/intron list; warn and pick closest region.
            # For MVP, choose the last region with start <= pos.
            candidates = [i for i, reg in enumerate(ordered) if int(reg["gene_start_idx"]) <= pos_gene0]
            if candidates:
                center_idx = candidates[-1]
                print(
                    f"[WARN] SNV pos_gene0={pos_gene0} not inside any region for {disease_id}; "
                    f"using closest previous region {ordered[center_idx]['region_id']}."
                )
            else:
                center_idx = 0
                print(
                    f"[WARN] SNV pos_gene0={pos_gene0} before first region for {disease_id}; using first region."
                )

        w_start, w_end = pick_5_region_window(center_idx, len(ordered))
        window_regs = ordered[w_start : w_end + 1]
        start_gene0 = int(window_regs[0]["gene_start_idx"])
        end_gene0 = int(window_regs[-1]["gene_end_idx"])
        region_ids = [r["region_id"] for r in window_regs]

        label = "default_context_5_regions"
        chosen_by = "default:+/-2_regions"

        window_id = stable_uuid(f"window:{disease_id}:{gene_id}:{start_gene0}-{end_gene0}:{label}")
        window_rows.append(
            {
                "window_id": window_id,
                "disease_id": disease_id,
                "gene_id": gene_id,
                "start_gene0": start_gene0,
                "end_gene0": end_gene0,
                "label": label,
                "chosen_by": chosen_by,
                "note": f"center_region={ordered[center_idx]['region_id']};regions={','.join(region_ids)}",
            }
        )

    print(f"[INFO] editing_target_window: {len(window_rows)}")

    if not args.dry_run:
        batch_upsert(sb, "editing_target_window", window_rows, batch_size=args.batch_size)

    print("[OK] Upload finished.")


if __name__ == "__main__":
    main()
