from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import numpy as np

from .constants import CENTER_INDEX, IN_LENGTH
from .genome import ReferenceGenome
from .utils import WindowMapping, rc


def extract_window_idx_mission6(
    genome: ReferenceGenome,
    chrom: str,
    center_pos_1b: int,
    strand: str,
    tx_start_1b: int,
    tx_end_1b: int,
    input_length: int = IN_LENGTH,
) -> str:
    """Exact Mission6 extract_window_idx() implementation.

    - Uses 0-based half-open [start, end) window centered at center_pos_1b.
    - Pads outside chromosome with 'N'.
    - Masks outside [TX_START, TX_END] with 'N' (taking strand reversal into account).
    """
    center_pos_0b = int(center_pos_1b) - 1
    half = input_length // 2

    # window in 0-based half-open
    start = center_pos_0b - half
    end = center_pos_0b + half  # exclusive

    fetch_start = max(0, start)
    fetch_end = max(fetch_start, end)

    seq = genome.fetch_seq(chrom, fetch_start, fetch_end, strand=strand)

    # left pad if start < 0
    left_pad = fetch_start - start
    if left_pad > 0:
        seq = ("N" * left_pad) + seq

    # length adjust
    if len(seq) < input_length:
        seq = seq + ("N" * (input_length - len(seq)))
    else:
        seq = seq[:input_length]

    # gene outside masking
    gene_start_0b = int(tx_start_1b) - 1
    gene_end_excl_0b = int(tx_end_1b)  # since 1-based inclusive -> 0-based exclusive

    overhang_left_genomic = max(0, gene_start_0b - start)
    overhang_right_genomic = max(0, end - gene_end_excl_0b)

    overhang_left_genomic = min(overhang_left_genomic, input_length)
    overhang_right_genomic = min(overhang_right_genomic, input_length)

    if strand == "+":
        left_n = overhang_left_genomic
        right_n = overhang_right_genomic
    else:
        left_n = overhang_right_genomic
        right_n = overhang_left_genomic

    if left_n > 0:
        seq = ("N" * left_n) + seq[left_n:]
    if right_n > 0:
        seq = seq[:-right_n] + ("N" * right_n)

    return seq


def apply_alt_at_center(seq_ref: str, alt_base_pos_strand: str, strand: str) -> str:
    """Return alt sequence by replacing seq_ref[CENTER_INDEX] with alt base.

    alt_base_pos_strand is always provided in positive strand.
    For '-' strand, we reverse-complement the single base before inserting.
    """
    alt = str(alt_base_pos_strand).upper()
    if len(alt) != 1:
        raise ValueError(f"alt must be single nucleotide, got: {alt_base_pos_strand!r}")
    if strand == "-":
        alt = rc(alt)
    seq_list = list(seq_ref)
    seq_list[CENTER_INDEX] = alt
    return "".join(seq_list)


def build_ref_alt_sequences_from_row(
    row: Dict[str, Any],
    genome: ReferenceGenome,
    tx_start_1b: int,
    tx_end_1b: int,
    input_length: int = IN_LENGTH,
    check_ref: bool = True,
) -> Tuple[str, str, WindowMapping]:
    """Build (ref_seq, alt_seq, mapping) from a variant row.

    Expected row keys:
      - chrom (str/int)
      - pos (1-based int)
      - strand ('+'/'-')
      - ref (single base, positive strand)
      - alt (single base, positive strand)
    """
    chrom = str(row["chrom"])
    pos_1b = int(row["pos"])
    strand = str(row["strand"])
    ref_pos = str(row.get("ref", "")).upper()
    alt_pos = str(row.get("alt", "")).upper()

    seq_ref = extract_window_idx_mission6(
        genome=genome,
        chrom=chrom,
        center_pos_1b=pos_1b,
        strand=strand,
        tx_start_1b=tx_start_1b,
        tx_end_1b=tx_end_1b,
        input_length=input_length,
    )

    # Optional ref check (in transcript orientation)
    if check_ref and ref_pos and len(ref_pos) == 1 and seq_ref[CENTER_INDEX] != "N":
        expected = ref_pos
        if strand == "-":
            expected = rc(expected)
        if seq_ref[CENTER_INDEX] != expected:
            raise ValueError(
                f"Ref base mismatch at center for {chrom}:{pos_1b}({strand}). "
                f"seq_center={seq_ref[CENTER_INDEX]!r} expected={expected!r} (ref_pos_strand={ref_pos!r})"
            )

    seq_alt = apply_alt_at_center(seq_ref, alt_pos, strand=strand)

    mapping = WindowMapping(chrom=chrom, pos_1b=pos_1b, strand=strand)
    return seq_ref, seq_alt, mapping
