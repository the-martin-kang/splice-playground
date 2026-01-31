#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Upload to Supabase (Postgres) using:
  - GRCh38.primary_assembly.genome.fa
  - refannotation_with_canonical.tsv
  - selected_gene_with_disease_name.tsv  (must have disease_name column)

Populates:
  - public.gene
  - public.region
  - public.disease
  - public.disease_gene
  - public.disease_representative_snv

Does NOT populate:
  - baseline_result, snv_result, user_state, user_state_result

Requirements:
  pip install pandas pyfaidx supabase

Env:
  export SUPABASE_URL="https://xxxx.supabase.co"
  export SUPABASE_SERVICE_KEY="service_role_key"
"""

import argparse
import os
from typing import Dict, List, Tuple, Any

import pandas as pd
from pyfaidx import Fasta
from supabase import create_client

DNA_COMP = str.maketrans("ACGTNacgtn", "TGCANtgcan")


def revcomp(seq: str) -> str:
    return seq.translate(DNA_COMP)[::-1]


def parse_coord_list(s: str) -> List[int]:
    parts = [p.strip() for p in str(s).split(",") if p.strip() != ""]
    return [int(p) for p in parts]


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
    # gene0 is 0-based index in transcript direction (5'->3')
    if strand == "+":
        return pos_chr1 - tx_start_1
    return tx_end_1 - pos_chr1


def region_chr_to_gene0_bounds(
    strand: str, tx_start_1: int, tx_end_1: int, start_chr1: int, end_chr1: int
) -> Tuple[int, int]:
    # returns (gene_start_idx, gene_end_idx) inclusive
    if strand == "+":
        return start_chr1 - tx_start_1, end_chr1 - tx_start_1
    return tx_end_1 - end_chr1, tx_end_1 - start_chr1


def pick_col(df: pd.DataFrame, candidates: List[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def batch_upsert(sb, table: str, rows: List[Dict[str, Any]], batch_size: int = 200) -> None:
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        if chunk:
            sb.table(table).upsert(chunk).execute()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fasta", required=True, help="GRCh38.primary_assembly.genome.fa (needs .fai)")
    ap.add_argument("--ref", required=True, help="refannotation_with_canonical.tsv")
    ap.add_argument("--selected", required=True, help="selected_gene_with_disease_name.tsv")
    ap.add_argument("--source-version", default="gencode.v46", help="gene.source_version value")
    ap.add_argument("--batch-size", type=int, default=200)

    ap.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL", ""))
    ap.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SERVICE_KEY", ""))
    args = ap.parse_args()

    if not args.supabase_url or not args.supabase_key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY (service role key) or pass via args.")

    # --- Load refannotation ---
    ref_df = pd.read_csv(args.ref, sep="\t")
    required_ref_cols = [
        "NAME", "CHROM", "STRAND", "TX_START", "TX_END", "EXON_START", "EXON_END",
        "canonical_transcript_id", "canonical_source"
    ]
    missing = [c for c in required_ref_cols if c not in ref_df.columns]
    if missing:
        raise SystemExit(f"refannotation_with_canonical.tsv missing columns: {missing}")

    ref_df["NAME"] = ref_df["NAME"].astype(str).str.strip()
    ref_by_name = {r["NAME"]: r for _, r in ref_df.iterrows()}

    # --- Load selected genes (variants + disease_name) ---
    sel_df = pd.read_csv(args.selected, sep="\t")
    sel_gene_col = pick_col(sel_df, ["gene", "NAME", "Gene", "gene_symbol"])
    sel_chrom_col = pick_col(sel_df, ["chrom", "CHROM", "chr"])
    sel_pos_col = pick_col(sel_df, ["pos", "POS", "position"])
    sel_ref_col = pick_col(sel_df, ["ref", "REF"])
    sel_alt_col = pick_col(sel_df, ["alt", "ALT"])
    sel_dname_col = pick_col(sel_df, ["disease_name"])

    if None in [sel_gene_col, sel_pos_col, sel_ref_col, sel_alt_col, sel_dname_col]:
        raise SystemExit(
            "selected TSV must contain gene,pos,ref,alt,disease_name.\n"
            f"Found columns: {list(sel_df.columns)}"
        )

    sel_df[sel_gene_col] = sel_df[sel_gene_col].astype(str).str.strip()
    sel_df[sel_dname_col] = sel_df[sel_dname_col].astype(str).str.strip()

    if (sel_df[sel_dname_col] == "").any():
        bad = sel_df[sel_df[sel_dname_col] == ""][[sel_gene_col, sel_pos_col, sel_ref_col, sel_alt_col]]
        raise SystemExit(f"Empty disease_name exists in selected file:\n{bad}")

    # --- FASTA ---
    fa = Fasta(args.fasta)
    fasta_has_chr = any(k.startswith("chr") for k in list(fa.keys())[:50])

    # --- Supabase ---
    sb = create_client(args.supabase_url, args.supabase_key)

    # Determine genes to upload
    genes_to_upload = sorted(set(sel_df[sel_gene_col].tolist()))
    missing_genes = [g for g in genes_to_upload if g not in ref_by_name]
    if missing_genes:
        raise SystemExit(f"Genes in selected file not found in refannotation_with_canonical.tsv: {missing_genes}")

    # =========================
    # 1) Upload gene + region
    # =========================
    gene_rows: List[Dict[str, Any]] = []
    region_rows: List[Dict[str, Any]] = []

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

        exon_starts = parse_coord_list(r["EXON_START"])
        exon_ends = parse_coord_list(r["EXON_END"])
        if len(exon_starts) != len(exon_ends):
            raise SystemExit(f"EXON_START/EXON_END mismatch for {gene_name}")
        exon_count = len(exon_starts)

        gene_id = gene_name  # gene_id == gene_symbol in this project
        gene_len = tx_end - tx_start + 1

        canonical_transcript_id = str(r["canonical_transcript_id"]) if pd.notna(r["canonical_transcript_id"]) else None
        canonical_source = str(r["canonical_source"]) if pd.notna(r["canonical_source"]) else None

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

        # Exons
        for i, (s, e) in enumerate(zip(exon_starts, exon_ends), start=1):
            s = int(s); e = int(e)
            if e < s:
                raise SystemExit(f"Exon end < start for {gene_name} exon{i}: {s},{e}")

            seq = fasta_slice_1based_inclusive(fa, chrom, s, e)
            if strand == "-":
                seq = revcomp(seq)

            gs, ge = region_chr_to_gene0_bounds(strand, tx_start, tx_end, s, e)
            length = e - s + 1
            if (ge - gs + 1) != length:
                raise SystemExit(f"Gene0 bounds length mismatch for {gene_name} exon{i}")

            region_rows.append({
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
            })

        # Introns (between exons)
        for i in range(1, exon_count):
            intron_start = int(exon_ends[i - 1]) + 1
            intron_end = int(exon_starts[i]) - 1
            if intron_end < intron_start:
                continue

            seq = fasta_slice_1based_inclusive(fa, chrom, intron_start, intron_end)
            if strand == "-":
                seq = revcomp(seq)

            gs, ge = region_chr_to_gene0_bounds(strand, tx_start, tx_end, intron_start, intron_end)
            length = intron_end - intron_start + 1
            if (ge - gs + 1) != length:
                raise SystemExit(f"Gene0 bounds length mismatch for {gene_name} intron{i}")

            region_rows.append({
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
            })

    print(f"[INFO] Upserting genes: {len(gene_rows)}")
    print(f"[INFO] Upserting regions: {len(region_rows)}")

    batch_upsert(sb, "gene", gene_rows, batch_size=args.batch_size)
    batch_upsert(sb, "region", region_rows, batch_size=args.batch_size)

    # =========================
    # 2) Upload disease + link + representative_snv
    # =========================
    disease_rows: List[Dict[str, Any]] = []
    disease_gene_rows: List[Dict[str, Any]] = []
    snv_rows: List[Dict[str, Any]] = []

    for _, v in sel_df.iterrows():
        gene_name = str(v[sel_gene_col]).strip()
        r = ref_by_name[gene_name]

        chrom_ref = normalize_chrom(r["CHROM"], fasta_has_chr)
        strand = str(r["STRAND"]).strip()
        tx_start = int(r["TX_START"])
        tx_end = int(r["TX_END"])

        pos_chr1 = int(v[sel_pos_col])  # 1-based chromosome coord
        ref_base = str(v[sel_ref_col]).strip().upper()
        alt_base = str(v[sel_alt_col]).strip().upper()
        disease_name = str(v[sel_dname_col]).strip()

        # Optional chrom sanity check if present
        if sel_chrom_col is not None and pd.notna(v[sel_chrom_col]):
            chrom_sel = normalize_chrom(v[sel_chrom_col], fasta_has_chr)
            if chrom_sel != chrom_ref:
                raise SystemExit(f"Chrom mismatch for {gene_name}: selected={chrom_sel}, ref={chrom_ref}")

        # Convert to gene0
        pos_gene0 = gene_pos_to_gene0(strand, tx_start, tx_end, pos_chr1)
        gene_len = tx_end - tx_start + 1
        if pos_gene0 < 0 or pos_gene0 >= gene_len:
            raise SystemExit(f"pos_gene0 out of gene range for {gene_name}: pos_chr1={pos_chr1}, pos_gene0={pos_gene0}")

        # Validate REF against FASTA at genomic position (chromosome orientation)
        fasta_ref = fasta_slice_1based_inclusive(fa, chrom_ref, pos_chr1, pos_chr1)
        if fasta_ref != ref_base:
            raise SystemExit(
                f"REF mismatch for {gene_name} at {chrom_ref}:{pos_chr1} FASTA={fasta_ref} != ref={ref_base}"
            )

        # disease_id = seed id (stable + unique)
        disease_id = f"{gene_name}_gene0_{pos_gene0}_{ref_base}>{alt_base}"

        disease_rows.append({
            "disease_id": disease_id,
            "disease_name": disease_name,
            "description": None,
            "image_path": None,
        })
        disease_gene_rows.append({
            "disease_id": disease_id,
            "gene_id": gene_name,
        })
        snv_rows.append({
            "disease_id": disease_id,
            "gene_id": gene_name,
            "pos_gene0": int(pos_gene0),
            "ref": ref_base,
            "alt": alt_base,
            "note": f"chr={chrom_ref};pos1={pos_chr1}",
        })

    print(f"[INFO] Upserting diseases: {len(disease_rows)}")
    batch_upsert(sb, "disease", disease_rows, batch_size=args.batch_size)

    print(f"[INFO] Upserting disease_gene links: {len(disease_gene_rows)}")
    batch_upsert(sb, "disease_gene", disease_gene_rows, batch_size=args.batch_size)

    print(f"[INFO] Upserting representative SNVs: {len(snv_rows)}")
    batch_upsert(sb, "disease_representative_snv", snv_rows, batch_size=args.batch_size)

    print("[OK] Upload finished.")


if __name__ == "__main__":
    main()