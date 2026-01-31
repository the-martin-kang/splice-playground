import argparse
import pandas as pd

def parse_int_list(s: str):
    if pd.isna(s):
        return []
    return [int(x.strip()) for x in str(s).split(",") if x.strip() != ""]

def parse_coord_list(s: str):
    # "123,456,789," 형태도 처리
    if pd.isna(s):
        return []
    parts = [p.strip() for p in str(s).split(",") if p.strip() != ""]
    return [int(p) for p in parts]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True, help="refannotation_with_canonical.tsv path")
    ap.add_argument("--show", type=int, default=50, help="max rows to show for skip genes")
    args = ap.parse_args()

    df = pd.read_csv(args.tsv, sep="\t")

    required = ["NAME", "EXON_START", "canonical_exon_numbers"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns in TSV: {missing}\nColumns={list(df.columns)}")

    rows = []
    for _, r in df.iterrows():
        name = str(r["NAME"]).strip()

        exon_starts = parse_coord_list(r["EXON_START"])
        exon_count = len(exon_starts)

        canon_exons = parse_int_list(r["canonical_exon_numbers"])
        canon_set = set(canon_exons)
        full_set = set(range(1, exon_count + 1))

        # canonical이 전체 exon을 모두 포함하는가?
        covers_all = (canon_set == full_set)

        # canonical이 subset이라면 missing exon이 존재(= exon skip이 canonical)
        missing_exons = sorted(list(full_set - canon_set))

        # canonical이 연속인가? (예: 1,2,3,5 -> 비연속)
        is_contiguous = (canon_exons == list(range(min(canon_exons), max(canon_exons) + 1))) if canon_exons else True

        # canonical에 이상치(범위 밖)가 있는가?
        out_of_range = sorted([x for x in canon_exons if x < 1 or x > exon_count])

        rows.append({
            "NAME": name,
            "exon_count": exon_count,
            "canonical_len": len(canon_exons),
            "covers_all_exons": covers_all,
            "is_contiguous": is_contiguous,
            "missing_exons": ",".join(map(str, missing_exons)) if missing_exons else "",
            "out_of_range": ",".join(map(str, out_of_range)) if out_of_range else "",
            "canonical_exon_numbers": ",".join(map(str, canon_exons)),
        })

    out = pd.DataFrame(rows)

    # 1) canonical이 전체 exon을 다 포함하지 않는 gene들 (즉, canonical exon skip 가능)
    skip_df = out[~out["covers_all_exons"]].copy()

    # 2) canonical이 비연속인 gene들
    noncontig_df = out[~out["is_contiguous"]].copy()

    # 3) 범위 밖 exon 번호가 있는 gene들(데이터 오류 가능)
    oor_df = out[out["out_of_range"] != ""].copy()

    print(f"[INFO] Total genes: {len(out)}")
    print(f"[INFO] Canonical includes ALL exons: {(out['covers_all_exons']).sum()} / {len(out)}")
    print(f"[INFO] Canonical is SUBSET (possible exon-skip canonical): {len(skip_df)}")
    print(f"[INFO] Canonical is NON-CONTIGUOUS: {len(noncontig_df)}")
    print(f"[INFO] Canonical has OUT-OF-RANGE exon numbers: {len(oor_df)}")
    print()

    if len(skip_df) > 0:
        print("=== Genes where canonical_exon_numbers does NOT cover all exons (possible exon-skip canonical) ===")
        print(skip_df[[
            "NAME","exon_count","canonical_len","missing_exons","canonical_exon_numbers"
        ]].head(args.show).to_string(index=False))
        print()

    if len(noncontig_df) > 0:
        print("=== Genes where canonical_exon_numbers is non-contiguous ===")
        print(noncontig_df[[
            "NAME","exon_count","canonical_len","canonical_exon_numbers"
        ]].head(args.show).to_string(index=False))
        print()

    if len(oor_df) > 0:
        print("=== Genes where canonical_exon_numbers has out-of-range values (data issue) ===")
        print(oor_df[[
            "NAME","exon_count","out_of_range","canonical_exon_numbers"
        ]].head(args.show).to_string(index=False))
        print()

if __name__ == "__main__":
    main()