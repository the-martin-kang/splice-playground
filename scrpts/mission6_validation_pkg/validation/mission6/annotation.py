from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .utils import WindowMapping, with_chr_prefix


def _parse_exon_coords(x: object) -> np.ndarray:
    """Parse Mission6-style EXON_START/EXON_END field.

    Mission6 TSV typically stores coordinates like: "123,456,789," (trailing comma).
    """
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.array([], dtype=np.int32)
    s = str(x)
    parts = [p for p in s.split(",") if p.strip() != ""]
    return np.asarray([int(p) for p in parts], dtype=np.int32)


@dataclass
class RefAnnotation:
    """Mission6_refannotation.tsv loader and helpers."""

    path: str

    def __post_init__(self) -> None:
        df = pd.read_csv(self.path, sep="\t")
        required = {"NAME", "CHROM", "STRAND", "TX_START", "TX_END", "EXON_START", "EXON_END"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Annotation TSV missing columns: {sorted(missing)}")

        # parse exon arrays
        df = df.copy()
        df["EXON_START"] = df["EXON_START"].apply(_parse_exon_coords)
        df["EXON_END"] = df["EXON_END"].apply(_parse_exon_coords)

        self.df = df
        self.df_by_gene = df.set_index("NAME")

        # Build chromosome index (like ann_index in your notebook)
        self.ann_index: Dict[str, Dict[str, object]] = {}
        for chrom, sub in df.groupby("CHROM"):
            sub = sub.sort_values("TX_START").reset_index(drop=True)
            self.ann_index[str(chrom)] = {
                "TX_START": sub["TX_START"].to_numpy(),
                "TX_END": sub["TX_END"].to_numpy(),
                "NAME": sub["NAME"].to_numpy(),
                "STRAND": sub["STRAND"].to_numpy(),
                "EXON_START": sub["EXON_START"].to_list(),
                "EXON_END": sub["EXON_END"].to_list(),
            }

    def get_gene_row(self, gene: str) -> pd.Series:
        return self.df_by_gene.loc[str(gene)]

    def find_gene_by_pos(self, chrom: str, pos_1b: int) -> Tuple[Optional[str], Optional[str]]:
        """Return (gene_name, strand) for a variant position, like Mission6 find_gene_by_pos()."""
        key = with_chr_prefix(str(chrom))
        if key not in self.ann_index:
            # try without chr
            key = str(chrom)
            if key not in self.ann_index:
                return None, None

        info = self.ann_index[key]
        tx_start = info["TX_START"]
        tx_end = info["TX_END"]
        names = info["NAME"]
        strands = info["STRAND"]

        mask = (tx_start <= pos_1b) & (tx_end >= pos_1b)
        if not mask.any():
            return None, None
        idx = int(np.where(mask)[0][0])
        return str(names[idx]), str(strands[idx])

    def gene0_pos(self, gene: str, pos_1b: int) -> int:
        """Compute gene0 (0-based in transcript direction) for pos_1b."""
        r = self.get_gene_row(gene)
        tx_start = int(r["TX_START"])
        tx_end = int(r["TX_END"])
        strand = str(r["STRAND"])
        if strand == "+":
            return pos_1b - tx_start
        return tx_end - pos_1b

    def splice_label_sites_1b(
        self,
        gene: str,
        donor_label_mode: str = "intron_start",
    ) -> Tuple[List[int], List[int]]:
        """Return (donor_sites_1b, acceptor_sites_1b) in 1-based genomic coords.

        donor_label_mode:
          - 'intron_start' (recommended): donor label is the *first intron base*.
              '+' : exon_end + 1
              '-' : exon_start - 1
          - 'exon_end': donor label is the *last exon base*.
              '+' : exon_end
              '-' : exon_start  (because exon ends at start in transcript direction)

        Acceptor label is always defined as the *first exon base in transcript direction*:
          '+' : exon_start
          '-' : exon_end
        """
        r = self.get_gene_row(gene)
        strand = str(r["STRAND"])
        exon_starts = list(map(int, r["EXON_START"]))
        exon_ends = list(map(int, r["EXON_END"]))
        if len(exon_starts) != len(exon_ends):
            raise ValueError(f"EXON_START/EXON_END length mismatch for gene={gene}")

        # order exons in transcript direction
        exons = list(zip(exon_starts, exon_ends))
        exons.sort(key=lambda x: x[0], reverse=(strand == "-"))

        donor_sites: List[int] = []
        acceptor_sites: List[int] = []

        for i in range(len(exons) - 1):
            (s1, e1) = exons[i]
            (s2, e2) = exons[i + 1]

            # acceptor: first base of exon2 in transcript direction
            if strand == "+":
                acc = s2
            else:
                acc = e2
            acceptor_sites.append(int(acc))

            # donor: first base of intron after exon1 (or last exon base if requested)
            if donor_label_mode not in {"intron_start", "exon_end"}:
                raise ValueError("donor_label_mode must be 'intron_start' or 'exon_end'")

            if donor_label_mode == "intron_start":
                if strand == "+":
                    don = e1 + 1
                else:
                    don = s1 - 1
            else:  # exon_end
                if strand == "+":
                    don = e1
                else:
                    don = s1
            donor_sites.append(int(don))

        return donor_sites, acceptor_sites
