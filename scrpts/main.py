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

if __name__ == "__main__":
    main()