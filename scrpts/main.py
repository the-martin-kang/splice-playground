<<<<<<< HEAD
def main():
    import pandas as pd

    p = "/Users/martin/Git/splice-playground/scrpts/data/refannotation_with_canonical.tsv"
    df = pd.read_csv(p, sep="\t")

    targets = {"SMN1", "SMN2", "MSH2", "CFTR", "DNM1", "TSC2", "PMM2"}
    sub = df[df["NAME"].isin(targets)].copy()

    def count_list_items(s) -> int:
        if pd.isna(s):
            return 0
        return len([x for x in str(s).split(",") if x.strip() != ""])

    # exon counts
    sub["EXON_COUNT"] = sub["EXON_START"].apply(count_list_items)
    sub["EXON_COUNT_END"] = sub["EXON_END"].apply(count_list_items)
    sub["EXON_COUNT_MATCH"] = sub["EXON_COUNT"] == sub["EXON_COUNT_END"]

    # gene length (inclusive)
    sub["GENE_LENGTH"] = sub["TX_END"].astype(int) - sub["TX_START"].astype(int) + 1

    out = sub[[
        "NAME",
        "CHROM",
        "STRAND",
        "TX_START",
        "TX_END",
        "GENE_LENGTH",
        "EXON_COUNT",
        "EXON_COUNT_MATCH",
        "canonical_transcript_id",
        "canonical_source",
        "canonical_exon_numbers",
    ]].sort_values("NAME")

    print(out.to_string(index=False))
=======
# def main():
#     import pandas as pd
#     p = "/Users/martin/Git/splice-playground/scrpts/data/refannotation_with_canonical.tsv"
#     df = pd.read_csv(p, sep="\t")
#     targets = {"SMN1", "SMN2", "MSH2", "CFTR", "DNM1", "TSC2", "PMM2"}
#     sub = df[df["NAME"].isin(targets)][
#         ["NAME", "canonical_transcript_id", "canonical_source", "canonical_exon_numbers"]]
#     print(sub.to_string(index=False))
#
#
# if __name__ == "__main__":
#     main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import pandas as pd

ANSWER_INDEX = {2, 8, 10, 16, 17, 21, 26, 34, 37, 38}  # 0-base
TARGET_GENES = {"MSH2", "CFTR", "DNM1", "TSC2", "PMM2"}  # SMN1/SMN2 제외

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-tsv", required=True, help="Mission6_finaltask.tsv path")
    ap.add_argument("--out-tsv", required=True, help="Output TSV path")
    ap.add_argument("--genes", default=",".join(sorted(TARGET_GENES)),
                    help="Comma-separated gene symbols to keep (default: MSH2,CFTR,DNM1,TSC2,PMM2)")
    args = ap.parse_args()

    genes = {g.strip() for g in args.genes.split(",") if g.strip()}

    df = pd.read_csv(args.in_tsv, sep="\t")

    # 필수 컬럼 체크
    required_cols = {"answer_index", "gene"}
    missing = required_cols - set(df.columns)
    if missing:
        raise SystemExit(f"Missing required columns: {sorted(missing)}")

    # 타입 정리
    df["answer_index"] = pd.to_numeric(df["answer_index"], errors="coerce").astype("Int64")
    df["gene"] = df["gene"].astype(str).str.strip()

    # 필터: 정답 인덱스 + 타깃 유전자
    out = df[df["answer_index"].isin(ANSWER_INDEX) & df["gene"].isin(genes)].copy()

    # 정렬 (보기 편하게)
    out = out.sort_values(["gene", "answer_index"]).reset_index(drop=True)

    out.to_csv(args.out_tsv, sep="\t", index=False)
    print(f"[OK] Wrote {len(out)} rows -> {args.out_tsv}")
    print(out[["answer_index", "gene"]].to_string(index=False))
>>>>>>> backend

if __name__ == "__main__":
    main()