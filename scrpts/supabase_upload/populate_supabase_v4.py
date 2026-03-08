#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Populate Supabase for splice-playground (v4)

Changes from v2:
- disease visibility / supported step / seed_mode supported
- splice_altering_snv supports allele_coordinate_system:
    * genomic_positive  (recommended for new rows)
    * gene_direction    (legacy-compatible)
- region sequences remain gene-direction oriented
- baseline_result stays DB-exon-number based (1..N)
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
ETL_NAMESPACE = uuid.UUID("25b13d80-93b0-4d17-9d4d-ded2c2f5f321")


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
    return str(fa[chrom][start_1 - 1 : end_1]).upper()


def gene_pos_to_gene0(strand: str, tx_start_1: int, tx_end_1: int, pos_chr1: int) -> int:
    if strand == "+":
        return pos_chr1 - tx_start_1
    return tx_end_1 - pos_chr1


def region_chr_to_gene0_bounds(strand: str, tx_start_1: int, tx_end_1: int, start_chr1: int, end_chr1: int) -> Tuple[int, int]:
    if strand == "+":
        return start_chr1 - tx_start_1, end_chr1 - tx_start_1
    return tx_end_1 - end_chr1, tx_end_1 - start_chr1


def chunked(seq: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def batch_upsert(sb, table: str, rows: List[Dict[str, Any]], batch_size: int = 50) -> None:
    for chunk in chunked(rows, batch_size):
        if not chunk:
            continue
        sb.table(table).upsert(chunk).execute()


def select_canonical_exons(exon_starts_all: List[int], exon_ends_all: List[int], canonical_exon_numbers: List[int]) -> List[Tuple[int, int]]:
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

    seen = set()
    uniq: List[Tuple[int, int]] = []
    for s, e in exons:
        key = (int(s), int(e))
        if key not in seen:
            seen.add(key)
            uniq.append(key)
    return uniq


def pick_5_region_window(center_idx: int, total: int) -> Tuple[int, int]:
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
    return (max(0, start), min(total - 1, end))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="refannotation_with_canonical.tsv")
    ap.add_argument("--fasta", required=True, help="GRCh38.primary_assembly.genome.fa")
    ap.add_argument("--selected", required=True, help="selected_gene.tsv")
    ap.add_argument("--source-version", default="gencode.v46")
    ap.add_argument("--baseline-model-version", default="annotation_canonical_v1")
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL", ""))
    ap.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SERVICE_KEY", ""))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.supabase_url or not args.supabase_key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY or pass via args.")

    ref_df = pd.read_csv(args.ref, sep="\t")
    required_ref_cols = [
        "NAME","CHROM","STRAND","TX_START","TX_END",
        "EXON_START","EXON_END","canonical_exon_numbers",
        "canonical_transcript_id","canonical_source"
    ]
    missing = [c for c in required_ref_cols if c not in ref_df.columns]
    if missing:
        raise SystemExit(f"refannotation_with_canonical.tsv missing columns: {missing}")
    ref_df["NAME"] = ref_df["NAME"].astype(str).str.strip()
    ref_by_name: Dict[str, Dict[str, Any]] = {r["NAME"]: r.to_dict() for _, r in ref_df.iterrows()}

    sel_df = pd.read_csv(args.selected, sep="\t")
    col_gene = pick_col(sel_df, ["gene","NAME","Gene","gene_symbol"])
    col_chrom = pick_col(sel_df, ["chrom","CHROM","chr"])
    col_pos = pick_col(sel_df, ["pos","POS","position"])
    col_ref = pick_col(sel_df, ["ref","REF"])
    col_alt = pick_col(sel_df, ["alt","ALT"])
    col_dname = pick_col(sel_df, ["disease_name"])
    col_strand = pick_col(sel_df, ["strand","STRAND"])
    if None in [col_gene, col_chrom, col_pos, col_ref, col_alt, col_dname]:
        raise SystemExit("selected TSV must contain: gene, chrom, pos, ref, alt, disease_name")

    # optional columns
    col_visible = pick_col(sel_df, ["is_visible_in_service"])
    col_maxstep = pick_col(sel_df, ["max_supported_step"])
    col_seed_mode = pick_col(sel_df, ["seed_mode"])
    col_image_path = pick_col(sel_df, ["image_path"])
    col_note = pick_col(sel_df, ["note"])
    col_acs = pick_col(sel_df, ["allele_coordinate_system"])  # genomic_positive / gene_direction

    sel_df[col_gene] = sel_df[col_gene].astype(str).str.strip()
    sel_df[col_dname] = sel_df[col_dname].astype(str).str.strip()

    genes_to_upload = sorted(set(sel_df[col_gene].tolist()))
    missing_genes = [g for g in genes_to_upload if g not in ref_by_name]
    if missing_genes:
        raise SystemExit(f"Genes in selected file not found in refannotation_with_canonical.tsv: {missing_genes}")

    fa = Fasta(args.fasta)
    fasta_has_chr = any(str(k).startswith("chr") for k in list(fa.keys())[:50])
    sb = create_client(args.supabase_url, args.supabase_key)

    # ---------------- gene / region / baseline_result
    gene_rows: List[Dict[str, Any]] = []
    region_rows: List[Dict[str, Any]] = []
    baseline_rows: List[Dict[str, Any]] = []
    region_order_by_gene: Dict[str, List[Dict[str, Any]]] = {}

    for gene_name in genes_to_upload:
        r = ref_by_name[gene_name]
        chrom = normalize_chrom(r["CHROM"], fasta_has_chr)
        strand = str(r["STRAND"]).strip()
        tx_start = int(r["TX_START"])
        tx_end = int(r["TX_END"])
        exon_starts_all = parse_coord_list(r["EXON_START"])
        exon_ends_all = parse_coord_list(r["EXON_END"])
        canonical_numbers = parse_int_list(r.get("canonical_exon_numbers"))
        exons = select_canonical_exons(exon_starts_all, exon_ends_all, canonical_numbers)
        exons.sort(key=lambda x: x[0], reverse=(strand == "-"))
        exon_count = len(exons)
        if exon_count <= 0:
            raise SystemExit(f"No exons found for {gene_name}")
        gene_id = gene_name
        gene_len = tx_end - tx_start + 1
        canonical_transcript_id = str(r["canonical_transcript_id"]) if pd.notna(r.get("canonical_transcript_id")) else None
        canonical_source = str(r["canonical_source"]) if pd.notna(r.get("canonical_source")) else None

        gene_rows.append({
            "gene_id": gene_id,
            "gene_symbol": gene_name,
            "chromosome": chrom,
            "strand": strand,
            "length": int(gene_len),
            "exon_count": int(exon_count),
            "canonical_transcript_id": canonical_transcript_id,
            "canonical_source": canonical_source,
            "source_version": args.source_version,
        })

        ordered_regions: List[Dict[str, Any]] = []
        exon_regions: List[Dict[str, Any]] = []
        for i, (s, e) in enumerate(exons, start=1):
            s = int(s); e = int(e)
            seq = fasta_slice_1based_inclusive(fa, chrom, s, e)
            if strand == "-":
                seq = revcomp(seq)
            gs, ge = region_chr_to_gene0_bounds(strand, tx_start, tx_end, s, e)
            row = {
                "region_id": f"{gene_id}_exon_{i}",
                "gene_id": gene_id,
                "region_type": "exon",
                "region_number": int(i),
                "gene_start_idx": int(gs),
                "gene_end_idx": int(ge),
                "length": int(e - s + 1),
                "sequence": seq,
                "cds_start_offset": None,
                "cds_end_offset": None,
            }
            exon_regions.append(row)

        intron_regions: List[Dict[str, Any]] = []
        for i in range(1, exon_count):
            s1, e1 = exons[i-1]
            s2, e2 = exons[i]
            intron_start = min(int(e1), int(e2)) + 1
            intron_end = max(int(s1), int(s2)) - 1
            if intron_end < intron_start:
                continue
            seq = fasta_slice_1based_inclusive(fa, chrom, intron_start, intron_end)
            if strand == "-":
                seq = revcomp(seq)
            gs, ge = region_chr_to_gene0_bounds(strand, tx_start, tx_end, intron_start, intron_end)
            intron_regions.append({
                "region_id": f"{gene_id}_intron_{i}",
                "gene_id": gene_id,
                "region_type": "intron",
                "region_number": int(i),
                "gene_start_idx": int(gs),
                "gene_end_idx": int(ge),
                "length": int(intron_end - intron_start + 1),
                "sequence": seq,
                "cds_start_offset": None,
                "cds_end_offset": None,
            })

        intron_by_num = {r["region_number"]: r for r in intron_regions}
        for i in range(1, exon_count + 1):
            ordered_regions.append(exon_regions[i-1])
            if i < exon_count and i in intron_by_num:
                ordered_regions.append(intron_by_num[i])
        region_order_by_gene[gene_id] = ordered_regions

        region_rows.extend(exon_regions)
        region_rows.extend(intron_regions)

        baseline_rows.append({
            "gene_id": gene_id,
            "step": "step3",
            "model_version": args.baseline_model_version,
            "result_payload": {
                "included_exons": list(range(1, exon_count + 1)),
                "excluded_exons": [],
                "canonical_transcript_id": canonical_transcript_id,
                "canonical_source": canonical_source,
                "note": "baseline step3 derived from canonical exon list (DB exon numbering; no splicing prediction)",
            },
        })

    if not args.dry_run:
        batch_upsert(sb, "gene", gene_rows, batch_size=args.batch_size)
        batch_upsert(sb, "region", region_rows, batch_size=max(5, min(args.batch_size, 25)))
        batch_upsert(sb, "baseline_result", baseline_rows, batch_size=args.batch_size)

    # ---------------- disease / snv / window
    disease_rows: Dict[str, Dict[str, Any]] = {}
    snv_rows: List[Dict[str, Any]] = []

    for _, v in sel_df.iterrows():
        gene_name = str(v[col_gene]).strip()
        r = ref_by_name[gene_name]
        chrom_ref = normalize_chrom(v[col_chrom], fasta_has_chr)
        chrom_from_ref = normalize_chrom(r["CHROM"], fasta_has_chr)
        if chrom_ref != chrom_from_ref:
            raise SystemExit(f"Chrom mismatch for {gene_name}: selected={chrom_ref}, ref={chrom_from_ref}")

        strand_ref = str(r["STRAND"]).strip()
        if col_strand is not None and pd.notna(v[col_strand]):
            strand_sel = str(v[col_strand]).strip()
            if strand_sel in {"+", "-"} and strand_sel != strand_ref:
                raise SystemExit(f"Strand mismatch for {gene_name}: selected={strand_sel}, ref={strand_ref}")

        tx_start = int(r["TX_START"])
        tx_end = int(r["TX_END"])
        pos_chr1 = int(v[col_pos])
        ref_in = str(v[col_ref]).strip().upper()
        alt_in = str(v[col_alt]).strip().upper()
        disease_name = str(v[col_dname]).strip()

        fasta_ref = fasta_slice_1based_inclusive(fa, chrom_ref, pos_chr1, pos_chr1)
        if fasta_ref != ref_in:
            raise SystemExit(f"REF mismatch for {gene_name} at {chrom_ref}:{pos_chr1}. FASTA={fasta_ref} != input_ref={ref_in}")

        pos_gene0 = gene_pos_to_gene0(strand_ref, tx_start, tx_end, pos_chr1)
        # disease_id uses the stored SNV coordinates/alleles. Here we keep external genomic-positive style.
        disease_id = f"{gene_name}_gene0_{pos_gene0}_{ref_in}>{alt_in}"

        disease_rows[disease_id] = {
            "disease_id": disease_id,
            "disease_name": disease_name,
            "description": None,
            "image_path": (None if col_image_path is None or pd.isna(v[col_image_path]) else str(v[col_image_path])),
            "gene_id": gene_name,
            "is_visible_in_service": (True if col_visible is None or pd.isna(v[col_visible]) else str(v[col_visible]).strip().lower() in {"true","1","yes","y"}),
            "max_supported_step": (3 if col_maxstep is None or pd.isna(v[col_maxstep]) else int(v[col_maxstep])),
            "seed_mode": ("apply_alt" if col_seed_mode is None or pd.isna(v[col_seed_mode]) else str(v[col_seed_mode]).strip()),
            "note": (None if col_note is None or pd.isna(v[col_note]) else str(v[col_note])),
        }

        acs = "genomic_positive"
        if col_acs is not None and pd.notna(v[col_acs]):
            acs = str(v[col_acs]).strip()
        if acs not in {"genomic_positive", "gene_direction"}:
            raise SystemExit(f"Invalid allele_coordinate_system for {gene_name}: {acs}")

        stored_ref = ref_in
        stored_alt = alt_in
        note = f"chrom={chrom_ref};pos1={pos_chr1};input_ref={ref_in};input_alt={alt_in}"
        if acs == "gene_direction" and strand_ref == "-":
            stored_ref = complement_base(ref_in)
            stored_alt = complement_base(alt_in)
            note += ";stored_as=gene_direction"
        elif acs == "gene_direction":
            note += ";stored_as=gene_direction"
        else:
            note += ";stored_as=genomic_positive"

        snv_id = stable_uuid(f"snv:{disease_id}:{gene_name}:{pos_gene0}:{stored_ref}>{stored_alt}:{acs}")
        snv_rows.append({
            "snv_id": snv_id,
            "disease_id": disease_id,
            "gene_id": gene_name,
            "pos_gene0": int(pos_gene0),
            "ref": stored_ref,
            "alt": stored_alt,
            "is_representative": True,
            "chromosome": chrom_ref,
            "pos_hg38_1": int(pos_chr1),
            "allele_coordinate_system": acs,
            "note": note,
        })

    if not args.dry_run:
        batch_upsert(sb, "disease", list(disease_rows.values()), batch_size=args.batch_size)
        batch_upsert(sb, "splice_altering_snv", snv_rows, batch_size=args.batch_size)

    # windows based on representative SNV
    window_rows: List[Dict[str, Any]] = []
    for snv in snv_rows:
        disease_id = snv["disease_id"]
        gene_id = snv["gene_id"]
        pos_gene0 = int(snv["pos_gene0"])
        ordered = region_order_by_gene[gene_id]
        center_idx = None
        for i, reg in enumerate(ordered):
            if int(reg["gene_start_idx"]) <= pos_gene0 <= int(reg["gene_end_idx"]):
                center_idx = i
                break
        if center_idx is None:
            center_idx = 0
        w_start, w_end = pick_5_region_window(center_idx, len(ordered))
        window_regs = ordered[w_start:w_end+1]
        start_gene0 = int(window_regs[0]["gene_start_idx"])
        end_gene0 = int(window_regs[-1]["gene_end_idx"])
        region_ids = [r["region_id"] for r in window_regs]
        window_id = stable_uuid(f"window:{disease_id}:{gene_id}:{start_gene0}-{end_gene0}:default_context_5_regions")
        window_rows.append({
            "window_id": window_id,
            "disease_id": disease_id,
            "gene_id": gene_id,
            "start_gene0": start_gene0,
            "end_gene0": end_gene0,
            "label": "default_context_5_regions",
            "chosen_by": "default:+/-2_regions",
            "note": f"center_region={ordered[center_idx]['region_id']};regions={','.join(region_ids)}",
        })
    if not args.dry_run:
        batch_upsert(sb, "editing_target_window", window_rows, batch_size=args.batch_size)

    print("[OK] Upload finished.")


if __name__ == "__main__":
    main()
