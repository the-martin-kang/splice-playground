#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import pandas as pd

ANSWER_INDEX = {2, 8, 10, 16, 17, 21, 26, 34, 37, 38}  # 0-base
TARGET_GENES = {"MSH2", "CFTR", "DNM1", "TSC2", "PMM2"}  # finaltask에서 사용할 gene

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-tsv", required=True, help="Mission6_finaltask.tsv path")
    ap.add_argument("--out-tsv", required=True, help="Output TSV path")
    ap.add_argument("--genes", default=",".join(sorted(TARGET_GENES)),
                    help="Comma-separated gene symbols to keep (default: MSH2,CFTR,DNM1,TSC2,PMM2)")
    args = ap.parse_args()

    genes = {g.strip() for g in args.genes.split(",") if g.strip()}

    df = pd.read_csv(args.in_tsv, sep="\t")

    required_cols = {"answer_index", "gene"}
    missing = required_cols - set(df.columns)
    if missing:
        raise SystemExit(f"Missing required columns: {sorted(missing)}")

    df["answer_index"] = pd.to_numeric(df["answer_index"], errors="coerce").astype("Int64")
    df["gene"] = df["gene"].astype(str).str.strip()

    out = df[df["answer_index"].isin(ANSWER_INDEX) & df["gene"].isin(genes)].copy()

    # answer_index 컬럼 제거
    out = out.drop(columns=["answer_index"])

    # 보기 편하게 정렬(가능하면 gene/pos 기준)
    sort_cols = [c for c in ["gene", "pos"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols).reset_index(drop=True)
    else:
        out = out.reset_index(drop=True)

    out.to_csv(args.out_tsv, sep="\t", index=False)
    print(f"[OK] Wrote {len(out)} rows -> {args.out_tsv}")
    print(out[["gene"]].value_counts().to_string())

if __name__ == "__main__":
    main()