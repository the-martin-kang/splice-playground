#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import pandas as pd

def parse_coord_list(s: str):
    parts = [p.strip() for p in str(s).split(",") if p.strip() != ""]
    return [int(p) for p in parts]

def pick_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

def ensure_column(df, colname, default=None):
    if colname not in df.columns:
        df[colname] = default
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-tsv", required=True, help="refannotation.tsv path")
    ap.add_argument("--selected-tsv", required=True, help="selected_gene.tsv path (input)")
    ap.add_argument("--out-tsv", required=True, help="output tsv path")

    ap.add_argument("--gene", default="SMN1", help="Gene symbol to add (default: SMN1)")
    ap.add_argument("--exon-number", type=int, default=8, help="Which exon number to use from EXON_START list (1-based). default: 8")
    ap.add_argument("--offset-in-exon", type=int, default=5, help="0-based offset inside the exon. +6 base => 5. default: 5")

    ap.add_argument("--ref", dest="ref_base", default="C", help="REF base (default: C)")
    ap.add_argument("--alt", dest="alt_base", default="T", help="ALT base (default: T)")
    args = ap.parse_args()

    ref_df = pd.read_csv(args.ref_tsv, sep="\t")
    sel_df = pd.read_csv(args.selected_tsv, sep="\t")

    # refannotation column detection
    name_col = pick_col(ref_df, ["NAME", "gene", "Gene", "gene_symbol"])
    chrom_col = pick_col(ref_df, ["CHROM", "chrom", "Chromosome", "chr"])
    strand_col = pick_col(ref_df, ["STRAND", "strand"])
    exon_start_col = pick_col(ref_df, ["EXON_START", "exon_start"])
    exon_end_col = pick_col(ref_df, ["EXON_END", "exon_end"])

    if name_col is None or exon_start_col is None:
        raise SystemExit("refannotation.tsv must contain NAME(or gene) and EXON_START columns.")
    if chrom_col is None or strand_col is None:
        raise SystemExit("refannotation.tsv must contain CHROM and STRAND columns.")
    if exon_end_col is None:
        raise SystemExit("refannotation.tsv must contain EXON_END column (for sanity check).")

    gene_symbol = args.gene.strip()
    hit = ref_df[ref_df[name_col].astype(str).str.strip() == gene_symbol]
    if hit.empty:
        raise SystemExit(f"Gene '{gene_symbol}' not found in {args.ref_tsv} (column={name_col})")
    if len(hit) > 1:
        print(f"[WARN] Multiple rows matched {gene_symbol}; using the first one.")

    row = hit.iloc[0]
    chrom = str(row[chrom_col]).strip()
    strand = str(row[strand_col]).strip()

    exon_starts = parse_coord_list(row[exon_start_col])
    exon_ends = parse_coord_list(row[exon_end_col])

    exon_n = args.exon_number
    if exon_n < 1 or exon_n > len(exon_starts):
        raise SystemExit(f"Requested exon_number={exon_n}, but EXON_START has {len(exon_starts)} exons for {gene_symbol}")
    if len(exon_starts) != len(exon_ends):
        raise SystemExit(f"EXON_START/EXON_END length mismatch for {gene_symbol}")

    exon_start_1base = exon_starts[exon_n - 1]
    exon_end_1base = exon_ends[exon_n - 1]
    pos_1base = exon_start_1base + args.offset_in_exon  # 0-based offset, keep pos 1-based

    # sanity: position inside exon
    if not (exon_start_1base <= pos_1base <= exon_end_1base):
        raise SystemExit(
            f"Computed pos={pos_1base} is outside exon{exon_n} range [{exon_start_1base},{exon_end_1base}]"
        )

    # selected table column detection
    col_gene = pick_col(sel_df, ["gene", "NAME", "Gene", "gene_symbol"])
    col_pos  = pick_col(sel_df, ["pos", "position", "POS"])
    col_ref  = pick_col(sel_df, ["ref", "REF"])
    col_alt  = pick_col(sel_df, ["alt", "ALT"])
    col_chrom = pick_col(sel_df, ["chrom", "CHROM", "chr"])
    col_strand = pick_col(sel_df, ["strand", "STRAND"])

    if col_gene is None or col_pos is None or col_ref is None or col_alt is None:
        raise SystemExit(
            "selected_gene.tsv must contain columns for gene/pos/ref/alt.\n"
            f"Found columns: {list(sel_df.columns)}"
        )

    # If chrom/strand columns don't exist, create canonical names 'chrom' and 'strand'
    if col_chrom is None:
        sel_df = ensure_column(sel_df, "chrom", None)
        col_chrom = "chrom"
    if col_strand is None:
        sel_df = ensure_column(sel_df, "strand", None)
        col_strand = "strand"

    new_row = {c: None for c in sel_df.columns}
    new_row[col_gene] = gene_symbol
    new_row[col_pos] = int(pos_1base)
    new_row[col_ref] = args.ref_base
    new_row[col_alt] = args.alt_base
    new_row[col_chrom] = chrom
    new_row[col_strand] = strand

    # Avoid duplicates
    dup = (
        (sel_df[col_gene].astype(str).str.strip() == gene_symbol) &
        (pd.to_numeric(sel_df[col_pos], errors="coerce") == int(pos_1base)) &
        (sel_df[col_ref].astype(str).str.strip().str.upper() == args.ref_base.upper()) &
        (sel_df[col_alt].astype(str).str.strip().str.upper() == args.alt_base.upper())
    )
    if dup.any():
        print("[INFO] Same SMN1 variant row already exists. Writing without adding duplicate.")
        out_df = sel_df
    else:
        out_df = pd.concat([sel_df, pd.DataFrame([new_row])], ignore_index=True)

    out_df.to_csv(args.out_tsv, sep="\t", index=False)

    print(f"[OK] Added {gene_symbol} (chrom={chrom}, strand={strand}) variant:")
    print(f"     exon{exon_n} start={exon_start_1base}, end={exon_end_1base}, offset={args.offset_in_exon} -> pos={pos_1base} (1-base)")
    print(f"[OK] Wrote: {args.out_tsv}")

if __name__ == "__main__":
    main()