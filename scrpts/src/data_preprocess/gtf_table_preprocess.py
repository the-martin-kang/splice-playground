#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Add canonical_exon_numbers, canonical_transcript_id, canonical_source to TA refannotation TSV
using GENCODE GTF (e.g., gencode.v46.primary_assembly.annotation.gtf).

Input (TA TSV): must contain at least columns:
  NAME, CHROM, STRAND, TX_START, TX_END, EXON_START, EXON_END
  - EXON_START / EXON_END are comma-separated 1-based inclusive coords (may end with a trailing comma)

Output:
  same TSV + 3 columns:
    canonical_exon_numbers (e.g., "1,3,4,5,8")
    canonical_transcript_id (e.g., "ENST00000...")
    canonical_source ("MANE_Select" | "Ensembl_canonical" | "longest_CDS" | "")

Canonical selection per gene_name:
  1) transcript with tag "MANE_Select"
  2) else transcript with tag "Ensembl_canonical"
  3) else protein_coding transcript with the longest CDS (sum of CDS segments)

Mapping canonical transcript exons -> TA "gene-defined exon list":
  - Prefer exact coordinate match [start,end]
  - Fallback to high-overlap match (>= 0.95 overlap ratio)
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

Attr = Dict[str, str]
Interval = Tuple[int, int]  # (start, end), 1-based inclusive


# ----------------------------
# Helpers
# ----------------------------
_attr_re = re.compile(r'\s*([A-Za-z0-9_]+)\s+"([^"]+)"\s*;')

def parse_gtf_attributes(attr_str: str) -> Attr:
    attrs: Attr = {}
    for m in _attr_re.finditer(attr_str):
        k, v = m.group(1), m.group(2)
        # GTF may contain repeated keys like "tag"; handle separately by reading all tags later
        if k not in attrs:
            attrs[k] = v
    return attrs

def extract_all_tags(attr_str: str) -> List[str]:
    # tag "X"; tag "Y";
    # also handles repeated keys not captured by parse_gtf_attributes
    return re.findall(r'\btag\s+"([^"]+)"\s*;', attr_str)

def strip_version(ensembl_id: str) -> str:
    # ENSG0000... .15  -> ENSG0000...
    return ensembl_id.split(".", 1)[0] if ensembl_id else ensembl_id

def parse_coord_list(s: str) -> List[int]:
    # "65419,65520,69037," -> [65419,65520,69037]
    parts = [p.strip() for p in s.split(",") if p.strip() != ""]
    return [int(p) for p in parts]

def overlap_len(a: Interval, b: Interval) -> int:
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    return max(0, e - s + 1)

def interval_len(x: Interval) -> int:
    return x[1] - x[0] + 1


# ----------------------------
# Data structures
# ----------------------------
@dataclass
class TranscriptInfo:
    gene_name: str
    gene_id: str
    transcript_id: str
    transcript_type: str
    tags: Set[str] = field(default_factory=set)
    exons: List[Interval] = field(default_factory=list)
    cds_len: int = 0


# ----------------------------
# GTF parsing
# ----------------------------
def parse_gtf(gtf_path: str) -> Tuple[
    Dict[str, List[str]],                    # gene_name -> list transcript_id
    Dict[str, TranscriptInfo],               # transcript_id -> info
]:
    """
    Parse only what we need:
      - transcript metadata (gene_name, transcript_type, tags)
      - exon coordinates per transcript
      - CDS length per transcript
    """
    gene_to_tx: Dict[str, List[str]] = defaultdict(list)
    tx_info: Dict[str, TranscriptInfo] = {}

    with open(gtf_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue
            chrom, source, feature, start_s, end_s, score, strand, frame, attrs_s = parts
            start = int(start_s)
            end = int(end_s)

            attrs = parse_gtf_attributes(attrs_s)
            tags = set(extract_all_tags(attrs_s))

            gene_name = attrs.get("gene_name", "")
            gene_id = strip_version(attrs.get("gene_id", ""))
            transcript_id = strip_version(attrs.get("transcript_id", ""))

            if not gene_name or not gene_id or not transcript_id:
                continue

            if feature == "transcript":
                transcript_type = attrs.get("transcript_type") or attrs.get("transcript_biotype") or ""
                if transcript_id not in tx_info:
                    tx_info[transcript_id] = TranscriptInfo(
                        gene_name=gene_name,
                        gene_id=gene_id,
                        transcript_id=transcript_id,
                        transcript_type=transcript_type,
                        tags=set(tags),
                    )
                    gene_to_tx[gene_name].append(transcript_id)
                else:
                    # update tags / type if we saw transcript line later
                    tx_info[transcript_id].tags |= tags
                    if transcript_type and not tx_info[transcript_id].transcript_type:
                        tx_info[transcript_id].transcript_type = transcript_type

            elif feature == "exon":
                info = tx_info.get(transcript_id)
                if info is None:
                    # create minimal record if transcript line not seen yet
                    transcript_type = attrs.get("transcript_type") or attrs.get("transcript_biotype") or ""
                    info = TranscriptInfo(
                        gene_name=gene_name,
                        gene_id=gene_id,
                        transcript_id=transcript_id,
                        transcript_type=transcript_type,
                        tags=set(tags),
                    )
                    tx_info[transcript_id] = info
                    gene_to_tx[gene_name].append(transcript_id)
                info.exons.append((start, end))

            elif feature == "CDS":
                info = tx_info.get(transcript_id)
                if info is None:
                    transcript_type = attrs.get("transcript_type") or attrs.get("transcript_biotype") or ""
                    info = TranscriptInfo(
                        gene_name=gene_name,
                        gene_id=gene_id,
                        transcript_id=transcript_id,
                        transcript_type=transcript_type,
                        tags=set(tags),
                    )
                    tx_info[transcript_id] = info
                    gene_to_tx[gene_name].append(transcript_id)
                info.cds_len += (end - start + 1)

    # normalize exon ordering (by genomic coordinate)
    for tid, info in tx_info.items():
        if info.exons:
            info.exons.sort(key=lambda x: (x[0], x[1]))

    # de-dup transcript lists per gene_name
    for g, lst in gene_to_tx.items():
        seen = set()
        uniq = []
        for tid in lst:
            if tid not in seen:
                uniq.append(tid)
                seen.add(tid)
        gene_to_tx[g] = uniq

    return gene_to_tx, tx_info


# ----------------------------
# Canonical selection
# ----------------------------
def select_canonical_transcript(
    gene_name: str,
    gene_to_tx: Dict[str, List[str]],
    tx_info: Dict[str, TranscriptInfo],
) -> Tuple[Optional[str], str]:
    txs = gene_to_tx.get(gene_name, [])
    if not txs:
        return None, ""

    # consider only protein_coding transcripts for our project
    protein_txs = [tid for tid in txs if (tx_info.get(tid) and tx_info[tid].transcript_type == "protein_coding")]

    # 1) MANE_Select
    for tid in protein_txs:
        if "MANE_Select" in tx_info[tid].tags:
            return tid, "MANE_Select"

    # 2) Ensembl_canonical
    for tid in protein_txs:
        if "Ensembl_canonical" in tx_info[tid].tags:
            return tid, "Ensembl_canonical"

    # 3) longest CDS among protein coding
    best_tid = None
    best_len = -1
    for tid in protein_txs:
        clen = tx_info[tid].cds_len
        if clen > best_len:
            best_len = clen
            best_tid = tid
    if best_tid is not None and best_len > 0:
        return best_tid, "longest_CDS"

    # fallback: if protein_coding exists but no CDS (rare)
    if protein_txs:
        return protein_txs[0], "longest_CDS"

    return None, ""


# ----------------------------
# Exon mapping: transcript exon -> TA exon number
# ----------------------------
def map_transcript_exons_to_ta_exon_numbers(
    ta_exons: List[Interval],
    tx_exons: List[Interval],
    min_overlap_ratio: float = 0.95,
) -> List[int]:
    """
    Return TA exon numbers (1-based) that correspond to exons used by the transcript.

    Strategy:
      - exact match preferred
      - else choose best overlap if ratio >= min_overlap_ratio
    """
    # quick lookup for exact match
    exact_map: Dict[Interval, int] = {}
    for i, e in enumerate(ta_exons, start=1):
        exact_map[e] = i

    mapped: List[int] = []
    used_i: Set[int] = set()

    for txe in tx_exons:
        if txe in exact_map:
            i = exact_map[txe]
            mapped.append(i)
            used_i.add(i)
            continue

        # overlap fallback
        best_i = None
        best_score = 0.0
        tx_len = interval_len(txe)
        for i, ge in enumerate(ta_exons, start=1):
            ov = overlap_len(txe, ge)
            if ov <= 0:
                continue
            # require that most of tx exon is covered
            score = ov / tx_len
            if score > best_score:
                best_score = score
                best_i = i

        if best_i is not None and best_score >= min_overlap_ratio:
            mapped.append(best_i)
            used_i.add(best_i)
        # else: unmapped (will be handled by caller/logging)

    # unique + sorted
    return sorted(set(mapped))


# ----------------------------
# Main TSV processing
# ----------------------------
def process_refannotation(
    ref_tsv: str,
    gtf_path: str,
    out_tsv: str,
    min_overlap_ratio: float,
) -> None:
    gene_to_tx, tx_info = parse_gtf(gtf_path)

    with open(ref_tsv, "r", encoding="utf-8") as fin:
        reader = csv.DictReader(fin, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        # append if missing
        for col in ["canonical_exon_numbers", "canonical_transcript_id", "canonical_source"]:
            if col not in fieldnames:
                fieldnames.append(col)

        rows = list(reader)

    # build quick set of gene names present in refannotation
    genes_in_ref = {r.get("NAME", "").strip() for r in rows if r.get("NAME")}
    # optional: warn about genes not in GTF mapping
    missing_in_gtf = [g for g in sorted(genes_in_ref) if g not in gene_to_tx]
    if missing_in_gtf:
        print(f"[WARN] {len(missing_in_gtf)} gene_name(s) not found in GTF gene_name mapping (showing up to 10): "
              f"{missing_in_gtf[:10]}", file=sys.stderr)

    for r in rows:
        gene_name = (r.get("NAME") or "").strip()
        if not gene_name:
            r["canonical_exon_numbers"] = ""
            r["canonical_transcript_id"] = ""
            r["canonical_source"] = ""
            continue

        # parse TA exon list
        try:
            exon_starts = parse_coord_list(r["EXON_START"])
            exon_ends = parse_coord_list(r["EXON_END"])
            if len(exon_starts) != len(exon_ends):
                raise ValueError("EXON_START/EXON_END length mismatch")
            ta_exons = list(zip(exon_starts, exon_ends))
        except Exception as e:
            print(f"[ERROR] Failed to parse exon list for gene {gene_name}: {e}", file=sys.stderr)
            r["canonical_exon_numbers"] = ""
            r["canonical_transcript_id"] = ""
            r["canonical_source"] = ""
            continue

        # choose canonical transcript
        canon_tid, canon_src = select_canonical_transcript(gene_name, gene_to_tx, tx_info)
        if canon_tid is None:
            print(f"[WARN] No protein_coding transcript found for gene_name={gene_name}", file=sys.stderr)
            r["canonical_exon_numbers"] = ""
            r["canonical_transcript_id"] = ""
            r["canonical_source"] = ""
            continue

        # map exons
        tx_exons = tx_info[canon_tid].exons
        if not tx_exons:
            print(f"[WARN] Canonical transcript has no exon lines: gene={gene_name}, tx={canon_tid}", file=sys.stderr)
            r["canonical_exon_numbers"] = ""
        else:
            mapped_nums = map_transcript_exons_to_ta_exon_numbers(
                ta_exons=ta_exons,
                tx_exons=tx_exons,
                min_overlap_ratio=min_overlap_ratio,
            )
            if not mapped_nums:
                print(f"[WARN] Exon mapping failed: gene={gene_name}, tx={canon_tid}. "
                      f"(Try lowering --min-overlap or check coordinate conventions.)", file=sys.stderr)
                r["canonical_exon_numbers"] = ""
            else:
                r["canonical_exon_numbers"] = ",".join(str(x) for x in mapped_nums)

        r["canonical_transcript_id"] = canon_tid
        r["canonical_source"] = canon_src

    with open(out_tsv, "w", encoding="utf-8", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] Wrote enhanced TSV: {out_tsv}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-tsv", required=True, help="TA refannotation TSV (e.g., refannotation.tsv)")
    ap.add_argument("--gtf", required=True, help="GENCODE/Ensembl GTF (e.g., gencode.v46.primary_assembly.annotation.gtf)")
    ap.add_argument("--out-tsv", required=True, help="Output enhanced TSV")
    ap.add_argument("--min-overlap", type=float, default=0.95, help="Overlap ratio threshold for exon mapping fallback (default: 0.95)")
    args = ap.parse_args()

    process_refannotation(
        ref_tsv=args.ref_tsv,
        gtf_path=args.gtf,
        out_tsv=args.out_tsv,
        min_overlap_ratio=args.min_overlap,
    )

if __name__ == "__main__":
    main()