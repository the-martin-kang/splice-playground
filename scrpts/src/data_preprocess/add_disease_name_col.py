#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import pandas as pd

DEFAULT_DISEASE_NAME = {
    "CFTR": "Cystic fibrosis",
    "MSH2": "Lynch syndrome",
    "DNM1": "DNM1-related developmental and epileptic encephalopathy",
    "TSC2": "Tuberous sclerosis complex",
    "PMM2": "PMM2-CDG",
    "SMN1": "Spinal muscular atrophy (SMA)",
}

def pick_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-tsv", required=True, help="selected_gene.tsv input path")
    ap.add_argument("--out-tsv", required=True, help="output path (with disease_name column)")
    args = ap.parse_args()

    df = pd.read_csv(args.in_tsv, sep="\t")

    gene_col = pick_col(df, ["gene", "NAME", "Gene", "gene_symbol"])
    if gene_col is None:
        raise SystemExit(f"Cannot find gene column in: {list(df.columns)}")

    # normalize gene symbols
    df[gene_col] = df[gene_col].astype(str).str.strip()

    if "disease_name" not in df.columns:
        df["disease_name"] = ""

    # fill only empty disease_name
    empty_mask = df["disease_name"].isna() | (df["disease_name"].astype(str).str.strip() == "")
    df.loc[empty_mask, "disease_name"] = df.loc[empty_mask, gene_col].map(DEFAULT_DISEASE_NAME)

    # fallback for genes not in mapping
    still_empty = df["disease_name"].isna() | (df["disease_name"].astype(str).str.strip() == "")
    df.loc[still_empty, "disease_name"] = df.loc[still_empty, gene_col].apply(lambda g: f"{g} seed")

    df.to_csv(args.out_tsv, sep="\t", index=False)
    print(f"[OK] Wrote: {args.out_tsv}")
    print(df[[gene_col, "disease_name"]].drop_duplicates().to_string(index=False))

if __name__ == "__main__":
    main()