#!/usr/bin/env python3
"""
build_spliceai_dataset.py

Low-RAM dataset builder for SpliceAI-style training (core=5000, flanking=10000 => input_len=15000).

Input:
  - annotation TSV (Mission6_refannotation.tsv or refannotation_with_canonical.tsv)
    Columns required:
      NAME, CHROM, STRAND, TX_START, TX_END, EXON_START, EXON_END
    (optional columns like canonical_transcript_id are supported)

  - genome FASTA (GRCh38.primary_assembly.genome.fa, hg19, etc.)
    Must be indexed by pyfaidx (it will create *.fai next to the fasta)

  - (optional but recommended) GTF:
      used ONLY to map transcript_id -> gene_id (ENSG...) so we can apply
      paralog_gene.txt filtering to the test split.

Output:
  - out_dir/
      train_000.h5, train_001.h5, ...
      val_000.h5, ...
      test_000.h5, ...
      dataset_stats.json

Each shard contains:
  - X : uint8 [N, input_len]   (A=0,C=1,G=2,T=3,N/other=4)
  - Y : uint8 [N, core_len]    (0=neither, 1=acceptor, 2=donor)
  - meta/* arrays (gene_name, transcript_id, gene_id, chrom, strand, tx_start_1b, tx_end_1b, core_start_0b)

Why uint8 codes instead of one-hot?
  - 1/4 disk usage vs one-hot, and far less RAM during preprocessing.
  - One-hot is generated on-the-fly during training (Colab/H100).

Notes on splice labels (forward reading direction):
  - acceptor label at exon start nucleotide (first base of exon)  => intron ends right before it (..AG|EXON..)
  - donor label at exon end nucleotide (last base of exon)        => intron starts right after it (..EXON|GT..)

Coordinate assumptions (matches your Mission6):
  - TX_START/TX_END and EXON_START/EXON_END are 1-based inclusive genomic coordinates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from pyfaidx import Fasta
from tqdm import tqdm

try:
    import h5py  # type: ignore
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: h5py. Install with:\n"
        "  pip install h5py\n"
        "or (uv):\n"
        "  uv pip install h5py\n"
    ) from e


# -------------------------
# Utils
# -------------------------

_RC_TABLE = str.maketrans({
    "A": "T", "C": "G", "G": "C", "T": "A", "N": "N",
    "a": "t", "c": "g", "g": "c", "t": "a", "n": "n",
})

def reverse_complement(seq: str) -> str:
    return seq.translate(_RC_TABLE)[::-1].upper()

def normalize_chrom(chrom: str) -> str:
    """
    Normalize for comparison (strip 'chr' prefix, uppercase).
    'chr1' -> '1', '1' -> '1', 'chrX' -> 'X'
    """
    c = chrom.strip()
    if c.lower().startswith("chr"):
        c = c[3:]
    return c.upper()

def is_primary_chrom(chrom_norm: str) -> bool:
    # allow 1..22, X, Y
    if chrom_norm in {"X", "Y"}:
        return True
    return chrom_norm.isdigit() and 1 <= int(chrom_norm) <= 22

def parse_int_list(csvish: str) -> List[int]:
    """
    Parse strings like '65419,65520,69037,' -> [65419,65520,69037]
    """
    if csvish is None:
        return []
    parts = [p for p in csvish.strip().split(",") if p.strip() != ""]
    out: List[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            continue
    return out

def strip_version(x: str) -> str:
    # ENST000003.12 -> ENST000003
    return x.split(".")[0] if isinstance(x, str) else x


def _resolve_chrom_key(chrom: str, fasta: Fasta) -> str:
    """
    Return a key present in FASTA matching chrom, tolerating chr/no-chr prefixes.
    """
    keys = fasta.keys() if hasattr(fasta, "keys") else fasta
    if chrom in keys:
        return chrom
    if chrom.startswith("chr") and chrom[3:] in keys:
        return chrom[3:]
    prefixed = "chr" + chrom
    if prefixed in keys:
        return prefixed
    raise KeyError(
        f"Chromosome '{chrom}' not found in FASTA index. Example keys: {list(keys)[:5]}"
    )


def fetch_seq(fasta: Fasta, chrom: str, start0: int, end0: int, strand: str) -> str:
    """
    Fetch 0-based half-open [start0, end0) genomic sequence, then orient to strand.
    """
    if start0 < 0 or end0 <= start0:
        return ""
    key = _resolve_chrom_key(chrom, fasta)
    # pyfaidx slicing is 0-based half-open
    seq = str(fasta[key][start0:end0]).upper()
    if strand == "-":
        seq = reverse_complement(seq)
    return seq


# Byte -> code LUT: A=0,C=1,G=2,T=3,others=4
_LUT = np.full(256, 4, dtype=np.uint8)
_LUT[ord("A")] = 0
_LUT[ord("C")] = 1
_LUT[ord("G")] = 2
_LUT[ord("T")] = 3
_LUT[ord("N")] = 4

def encode_seq_to_uint8(seq: str) -> np.ndarray:
    """
    Fast encoding of DNA string to uint8 codes using a lookup table.
    """
    b = np.frombuffer(seq.encode("ascii", errors="ignore"), dtype=np.uint8)
    return _LUT[b]


# -------------------------
# GTF transcript->gene mapping (for paralog filtering)
# -------------------------

_GTF_RE_GENE_ID = re.compile(r'gene_id "([^"]+)"')
_GTF_RE_TX_ID = re.compile(r'transcript_id "([^"]+)"')

def load_transcript_to_gene_map(gtf_path: Path) -> Dict[str, str]:
    """
    Returns dict: transcript_id_nover -> gene_id_nover
    """
    mapping: Dict[str, str] = {}
    with gtf_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 9:
                continue
            attr = fields[8]
            m_tx = _GTF_RE_TX_ID.search(attr)
            m_gene = _GTF_RE_GENE_ID.search(attr)
            if not m_tx or not m_gene:
                continue
            tx = strip_version(m_tx.group(1))
            gene = strip_version(m_gene.group(1))
            if tx and gene and tx not in mapping:
                mapping[tx] = gene
    return mapping


def load_paralog_gene_ids(path: Path) -> set[str]:
    """
    paralog_gene.txt format (your file): first line header, then ENSG...
    """
    ids: set[str] = set()
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.lower().startswith("gene"):
                continue
            if s.startswith("ENSG"):
                ids.add(strip_version(s))
    return ids


# -------------------------
# HDF5 writer (sharded)
# -------------------------

@dataclass
class ShardConfig:
    input_len: int
    core_len: int
    compression: str
    chunk_rows: int
    max_samples_per_shard: int

class H5ShardWriter:
    """
    Append-only writer for a single HDF5 shard file.
    """
    def __init__(self, out_path: Path, cfg: ShardConfig):
        self.out_path = out_path
        self.cfg = cfg
        self.h5 = h5py.File(str(out_path), "w")

        # resizeable datasets
        maxshape_x = (None, cfg.input_len)
        maxshape_y = (None, cfg.core_len)

        self.X = self.h5.create_dataset(
            "X",
            shape=(0, cfg.input_len),
            maxshape=maxshape_x,
            dtype="u1",
            chunks=(cfg.chunk_rows, cfg.input_len),
            compression=cfg.compression,
        )
        self.Y = self.h5.create_dataset(
            "Y",
            shape=(0, cfg.core_len),
            maxshape=maxshape_y,
            dtype="u1",
            chunks=(cfg.chunk_rows, cfg.core_len),
            compression=cfg.compression,
        )

        # metadata group
        mg = self.h5.create_group("meta")
        self.meta_gene_name = mg.create_dataset(
            "gene_name", shape=(0,), maxshape=(None,), dtype="S32", chunks=(cfg.chunk_rows,)
        )
        self.meta_transcript_id = mg.create_dataset(
            "transcript_id", shape=(0,), maxshape=(None,), dtype="S32", chunks=(cfg.chunk_rows,)
        )
        self.meta_gene_id = mg.create_dataset(
            "gene_id", shape=(0,), maxshape=(None,), dtype="S32", chunks=(cfg.chunk_rows,)
        )
        self.meta_chrom = mg.create_dataset(
            "chrom", shape=(0,), maxshape=(None,), dtype="S8", chunks=(cfg.chunk_rows,)
        )
        self.meta_strand = mg.create_dataset(
            "strand", shape=(0,), maxshape=(None,), dtype="i1", chunks=(cfg.chunk_rows,)
        )
        self.meta_tx_start = mg.create_dataset(
            "tx_start_1b", shape=(0,), maxshape=(None,), dtype="i4", chunks=(cfg.chunk_rows,)
        )
        self.meta_tx_end = mg.create_dataset(
            "tx_end_1b", shape=(0,), maxshape=(None,), dtype="i4", chunks=(cfg.chunk_rows,)
        )
        self.meta_core_start = mg.create_dataset(
            "core_start_0b", shape=(0,), maxshape=(None,), dtype="i4", chunks=(cfg.chunk_rows,)
        )

        self.n = 0  # number of samples

    def append_batch(
        self,
        X_batch: np.ndarray,
        Y_batch: np.ndarray,
        gene_name: List[str],
        transcript_id: List[str],
        gene_id: List[str],
        chrom: List[str],
        strand: List[int],
        tx_start_1b: List[int],
        tx_end_1b: List[int],
        core_start_0b: List[int],
    ) -> None:
        b = X_batch.shape[0]
        if b == 0:
            return
        new_n = self.n + b

        # resize datasets
        self.X.resize((new_n, self.cfg.input_len))
        self.Y.resize((new_n, self.cfg.core_len))
        self.meta_gene_name.resize((new_n,))
        self.meta_transcript_id.resize((new_n,))
        self.meta_gene_id.resize((new_n,))
        self.meta_chrom.resize((new_n,))
        self.meta_strand.resize((new_n,))
        self.meta_tx_start.resize((new_n,))
        self.meta_tx_end.resize((new_n,))
        self.meta_core_start.resize((new_n,))

        sl = slice(self.n, new_n)
        self.X[sl, :] = X_batch
        self.Y[sl, :] = Y_batch

        self.meta_gene_name[sl] = np.array([s.encode("ascii", "ignore")[:32] for s in gene_name], dtype="S32")
        self.meta_transcript_id[sl] = np.array([s.encode("ascii", "ignore")[:32] for s in transcript_id], dtype="S32")
        self.meta_gene_id[sl] = np.array([s.encode("ascii", "ignore")[:32] for s in gene_id], dtype="S32")
        self.meta_chrom[sl] = np.array([s.encode("ascii", "ignore")[:8] for s in chrom], dtype="S8")
        self.meta_strand[sl] = np.array(strand, dtype="i1")
        self.meta_tx_start[sl] = np.array(tx_start_1b, dtype="i4")
        self.meta_tx_end[sl] = np.array(tx_end_1b, dtype="i4")
        self.meta_core_start[sl] = np.array(core_start_0b, dtype="i4")

        self.n = new_n

    def close(self) -> None:
        self.h5.flush()
        self.h5.close()


class ShardedWriter:
    """
    Manages multiple HDF5 shard files for a split (train/val/test).
    """
    def __init__(self, out_dir: Path, split: str, cfg: ShardConfig):
        self.out_dir = out_dir
        self.split = split
        self.cfg = cfg
        self.shard_idx = 0
        self.writer: Optional[H5ShardWriter] = None
        self.total_samples = 0
        self._open_new_shard()

    def _open_new_shard(self) -> None:
        if self.writer is not None:
            self.writer.close()
        out_path = self.out_dir / f"{self.split}_{self.shard_idx:03d}.h5"
        self.writer = H5ShardWriter(out_path, self.cfg)
        self.shard_idx += 1

    def append_batch(self, *args, **kwargs) -> None:
        assert self.writer is not None
        # If current shard would exceed limit, open new shard first.
        X_batch = args[0]
        b = int(X_batch.shape[0])
        if self.writer.n + b > self.cfg.max_samples_per_shard and self.writer.n > 0:
            self.total_samples += self.writer.n
            self._open_new_shard()
        self.writer.append_batch(*args, **kwargs)

    def close(self) -> None:
        if self.writer is not None:
            self.total_samples += self.writer.n
            self.writer.close()
            self.writer = None


# -------------------------
# Label building
# -------------------------

def build_labels(
    strand: str,
    tx_start_1b: int,
    tx_end_1b: int,
    exon_starts_1b: List[int],
    exon_ends_1b: List[int],
) -> np.ndarray:
    """
    Build per-position class labels (0=neither, 1=acceptor, 2=donor) along transcript (pre-mRNA) sequence.

    **Important convention (Week10 / SpliceAI-style preprocessing):**
      - acceptor label is placed on the *first base of an exon*
      - donor label is placed on the *last base of an exon*
      - BUT we do **not** label:
          * exon1 acceptor  (no upstream intron)
          * last exon donor (no downstream intron)

    We therefore skip by **exon order**, not by (idx==0 / idx==L-1) only.
    This matters when TX_START/TX_END are not exactly the first/last exon boundary
    (e.g. if your annotation has a small prefix before exon1, like MSH2).

    Transcript-oriented idx0 mapping:
      + strand: idx0 = gpos_1b - tx_start_1b
      - strand: idx0 = tx_end_1b - gpos_1b   (because transcript is reverse-complemented)
               exon start in transcript corresponds to genomic exon_end,
               exon end in transcript corresponds to genomic exon_start.
    """
    L = tx_end_1b - tx_start_1b + 1
    y = np.zeros(L, dtype=np.uint8)

    if len(exon_starts_1b) != len(exon_ends_1b) or L <= 0:
        return y

    # Convert exon bounds to transcript-oriented idx0 (inclusive)
    exons_idx0: List[Tuple[int, int]] = []
    for es, ee in zip(exon_starts_1b, exon_ends_1b):
        if strand == "+":
            s0 = int(es - tx_start_1b)
            e0 = int(ee - tx_start_1b)
        else:
            s0 = int(tx_end_1b - ee)
            e0 = int(tx_end_1b - es)
        exons_idx0.append((s0, e0))

    # transcript order (5'->3')
    exons_idx0.sort(key=lambda x: x[0])
    n_exons = len(exons_idx0)

    for exon_idx, (s0, e0) in enumerate(exons_idx0):
        # acceptor: exon start (skip exon1)
        if exon_idx > 0 and 0 <= s0 < L:
            y[s0] = 1

        # donor: exon end (skip last exon)
        if exon_idx < (n_exons - 1) and 0 <= e0 < L:
            y[e0] = 2

    return y
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--annotation", required=True, type=Path, help="TSV with TX/EXON coords (Mission6_refannotation.tsv or refannotation_with_canonical.tsv)")
    p.add_argument("--fasta", required=True, type=Path, help="Reference genome FASTA (indexed by pyfaidx)")
    p.add_argument("--out", required=True, type=Path, help="Output directory for HDF5 shards")

    # For paralog filtering
    p.add_argument("--gtf", type=Path, default=None, help="(optional) GTF to map transcript_id->gene_id for paralog filtering")
    p.add_argument("--paralog", type=Path, default=None, help="(optional) paralog_gene.txt (ENSG...). If provided, --gtf is REQUIRED.")

    # Dataset geometry
    p.add_argument("--flank", type=int, default=10000, help="Flanking context size (80/400/2000/10000). input_len = core_len + flank")
    p.add_argument("--core-len", type=int, default=5000, help="Core length (SpliceAI uses 5000)")

    # Split
    p.add_argument("--test-chrs", type=str, default="1,3,5,7,9", help="Comma-separated chromosomes for TEST split (default: 1,3,5,7,9)")
    p.add_argument(
        "--val-frac",
        type=float,
        default=0.1,
        help="Validation fraction sampled from TRAINING chromosomes (default: 0.1). Week10-style: random 10%% from train.",
    )
    p.add_argument("--val-seed", type=int, default=42, help="Seed for deterministic train/val split (default: 42)")
    p.add_argument("--include-nonprimary", action="store_true", help="Include non-primary contigs (chrUn etc). Default: skip.")

    # Sharding + compression
    p.add_argument("--compression", type=str, default="lzf", choices=["lzf", "gzip", "none"], help="HDF5 compression (lzf is fast)")
    p.add_argument("--chunk-rows", type=int, default=256, help="HDF5 chunk rows (affects write speed)")
    p.add_argument("--max-samples-per-shard", type=int, default=50000, help="Start a new shard after this many samples")
    p.add_argument("--write-batch", type=int, default=512, help="How many samples to buffer before writing to HDF5")

    # Debug
    p.add_argument("--max-rows", type=int, default=0, help="If >0, process only first N rows of annotation (debug)")
    p.add_argument("--motif-sanity", action="store_true", help="Count GT/GC (donor) and AG (acceptor) motifs around labeled sites")

    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    core_len = int(args.core_len)
    flank = int(args.flank)
    if flank % 2 != 0:
        raise SystemExit("--flank must be even (SpliceAI uses symmetrical left/right flanks).")
    flank_half = flank // 2
    input_len = core_len + flank

    # Split sets: chromosome-based TEST + random VAL from remaining (Week10-style)
    test_set = {normalize_chrom(c) for c in args.test_chrs.split(",") if c.strip()}
    val_frac = float(args.val_frac)
    if not (0.0 <= val_frac < 1.0):
        raise SystemExit("--val-frac must be in [0, 1).")
    val_seed = int(args.val_seed)

    # Paralog filtering
    tx2gene: Dict[str, str] = {}
    paralog_genes: set[str] = set()
    if args.paralog is not None:
        if args.gtf is None:
            raise SystemExit("If --paralog is provided, you must also provide --gtf (to map transcript_id -> gene_id).")
        paralog_genes = load_paralog_gene_ids(args.paralog)
        print(f"[INFO] Loaded paralog gene IDs: {len(paralog_genes):,}")
        tx2gene = load_transcript_to_gene_map(args.gtf)
        print(f"[INFO] Built transcript->gene map: {len(tx2gene):,}")

    # FASTA index
    fasta = Fasta(str(args.fasta), as_raw=True, sequence_always_upper=True)
    print(f"[INFO] FASTA loaded. Example keys: {list(fasta.keys())[:5]}")

    # Writers
    compression = None if args.compression == "none" else args.compression
    cfg = ShardConfig(
        input_len=input_len,
        core_len=core_len,
        compression=compression,
        chunk_rows=int(args.chunk_rows),
        max_samples_per_shard=int(args.max_samples_per_shard),
    )
    writers = {
        "train": ShardedWriter(out_dir, "train", cfg),
        "val": ShardedWriter(out_dir, "val", cfg),
        "test": ShardedWriter(out_dir, "test", cfg),
    }

    # Stats
    stats = {
        "core_len": core_len,
        "flank": flank,
        "input_len": input_len,
        "test_chrs": sorted(list(test_set)),
        "val_frac": val_frac,
        "val_seed": val_seed,
        "splits": {"train": 0, "val": 0, "test": 0},
        "label_counts": {
            "train": [0, 0, 0],
            "val": [0, 0, 0],
            "test": [0, 0, 0],
        },
        "motif": {
            "train": {},
            "val": {},
            "test": {},
        },
        "skipped": {
            "nonprimary_chrom": 0,
            "paralog_in_test": 0,
            "no_sequence": 0,
        }
    }

    donor_motif_counts = {"GT": 0, "GC": 0, "other": 0, "total": 0}
    acceptor_motif_counts = {"AG": 0, "other": 0, "total": 0}

    def _stable_uniform_0_1(key: str) -> float:
        """Deterministic uniform[0,1) from (seed, key)."""
        h = hashlib.md5(f"{val_seed}:{key}".encode("utf-8")).hexdigest()
        # 32-bit bucket -> [0,1)
        return int(h[:8], 16) / 0x1_0000_0000

    def _row_key(
        gene_name: str,
        tx_id: str,
        chrom_norm: str,
        strand: str,
        tx_start_1b: int,
        tx_end_1b: int,
    ) -> str:
        # Prefer transcript id if available; else fall back to a composite key
        if tx_id:
            return tx_id
        return f"{gene_name}|{chrom_norm}|{strand}|{tx_start_1b}|{tx_end_1b}"

    def split_for_row(
        chrom_norm: str,
        gene_name: str,
        tx_id: str,
        strand: str,
        tx_start_1b: int,
        tx_end_1b: int,
    ) -> str:
        """Chromosome-based TEST split + random VAL split from remaining (Week10-style)."""
        if chrom_norm in test_set:
            return "test"
        if val_frac <= 0.0:
            return "train"
        u = _stable_uniform_0_1(_row_key(gene_name, tx_id, chrom_norm, strand, tx_start_1b, tx_end_1b))
        return "val" if u < val_frac else "train"

    # Read annotation
    n_rows = 0
    with args.annotation.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in tqdm(reader, desc="Transcripts", unit="tx"):
            n_rows += 1
            if args.max_rows and n_rows > int(args.max_rows):
                break

            gene_name = row.get("NAME", "") or ""
            chrom = row.get("CHROM", "") or ""
            strand = row.get("STRAND", "+") or "+"
            tx_start_1b = int(row["TX_START"])
            tx_end_1b = int(row["TX_END"])

            chrom_norm = normalize_chrom(chrom)
            if not args.include_nonprimary and not is_primary_chrom(chrom_norm):
                stats["skipped"]["nonprimary_chrom"] += 1
                continue

            # transcript_id (optional)
            tx_id = row.get("canonical_transcript_id") or row.get("transcript_id") or ""
            tx_id = strip_version(tx_id) if tx_id else ""

            split = split_for_row(
                chrom_norm,
                gene_name,
                tx_id,
                strand,
                tx_start_1b,
                tx_end_1b,
            )

            gene_id = ""
            if tx_id and tx2gene:
                gene_id = tx2gene.get(strip_version(tx_id), "")
            if split == "test" and paralog_genes and gene_id and gene_id in paralog_genes:
                stats["skipped"]["paralog_in_test"] += 1
                continue

            exon_starts = parse_int_list(row.get("EXON_START", ""))
            exon_ends = parse_int_list(row.get("EXON_END", ""))
            if not exon_starts or not exon_ends:
                # no exons? skip
                continue

            # Fetch transcript (pre-mRNA) sequence including introns: [TX_START..TX_END] inclusive
            start0 = tx_start_1b - 1
            end0 = tx_end_1b
            seq = fetch_seq(fasta, chrom, start0, end0, strand=strand)
            if not seq:
                stats["skipped"]["no_sequence"] += 1
                continue
            L = len(seq)

            # Build labels for original length L
            y = build_labels(strand, tx_start_1b, tx_end_1b, exon_starts, exon_ends)

            # Optional motif sanity counts (only within original L, before padding)
            if args.motif_sanity:
                # acceptor motif: seq[acc-2:acc] == 'AG'
                # donor motif: seq[don+1:don+3] in {'GT','GC'}
                acc_pos = np.where(y == 1)[0]
                for p0 in acc_pos:
                    acceptor_motif_counts["total"] += 1
                    if p0 - 2 >= 0 and seq[p0-2:p0] == "AG":
                        acceptor_motif_counts["AG"] += 1
                    else:
                        acceptor_motif_counts["other"] += 1
                don_pos = np.where(y == 2)[0]
                for p0 in don_pos:
                    donor_motif_counts["total"] += 1
                    if p0 + 3 <= L and seq[p0+1:p0+3] == "GT":
                        donor_motif_counts["GT"] += 1
                    elif p0 + 3 <= L and seq[p0+1:p0+3] == "GC":
                        donor_motif_counts["GC"] += 1
                    else:
                        donor_motif_counts["other"] += 1

            # Pad transcript to a multiple of core_len (so all chunks have consistent length)
            L_pad = int(math.ceil(L / core_len) * core_len)
            pad_n = L_pad - L
            if pad_n > 0:
                seq_pad = seq + ("N" * pad_n)
                y_pad = np.pad(y, (0, pad_n), mode="constant", constant_values=0)
            else:
                seq_pad = seq
                y_pad = y

            assert len(seq_pad) == L_pad
            assert len(y_pad) == L_pad

            # Add flanks
            padded = ("N" * flank_half) + seq_pad + ("N" * flank_half)
            assert len(padded) == L_pad + flank

            # Build per-chunk samples
            # core_start ranges over padded transcript (excluding flanks) in steps of core_len
            X_buf: List[np.ndarray] = []
            Y_buf: List[np.ndarray] = []
            meta_gene_name: List[str] = []
            meta_tx_id: List[str] = []
            meta_gene_id: List[str] = []
            meta_chrom: List[str] = []
            meta_strand: List[int] = []
            meta_tx_start: List[int] = []
            meta_tx_end: List[int] = []
            meta_core_start: List[int] = []

            for core_start in range(0, L_pad, core_len):
                window = padded[core_start: core_start + input_len]
                if len(window) != input_len:
                    # should not happen due to padding
                    continue
                X_buf.append(encode_seq_to_uint8(window))
                Y_buf.append(y_pad[core_start: core_start + core_len])

                meta_gene_name.append(gene_name)
                meta_tx_id.append(tx_id)
                meta_gene_id.append(gene_id)
                meta_chrom.append(chrom)
                meta_strand.append(1 if strand == "+" else -1)
                meta_tx_start.append(tx_start_1b)
                meta_tx_end.append(tx_end_1b)
                meta_core_start.append(core_start)

                if len(X_buf) >= int(args.write_batch):
                    Xb = np.stack(X_buf, axis=0).astype(np.uint8, copy=False)
                    Yb = np.stack(Y_buf, axis=0).astype(np.uint8, copy=False)
                    writers[split].append_batch(
                        Xb, Yb,
                        meta_gene_name, meta_tx_id, meta_gene_id, meta_chrom,
                        meta_strand, meta_tx_start, meta_tx_end, meta_core_start,
                    )
                    # label counts
                    bc = np.bincount(Yb.reshape(-1), minlength=3)
                    stats["label_counts"][split] = (np.array(stats["label_counts"][split]) + bc).tolist()
                    stats["splits"][split] += int(Xb.shape[0])
                    # reset buffers
                    X_buf.clear(); Y_buf.clear()
                    meta_gene_name.clear(); meta_tx_id.clear(); meta_gene_id.clear()
                    meta_chrom.clear(); meta_strand.clear(); meta_tx_start.clear(); meta_tx_end.clear(); meta_core_start.clear()

            # flush remainder
            if X_buf:
                Xb = np.stack(X_buf, axis=0).astype(np.uint8, copy=False)
                Yb = np.stack(Y_buf, axis=0).astype(np.uint8, copy=False)
                writers[split].append_batch(
                    Xb, Yb,
                    meta_gene_name, meta_tx_id, meta_gene_id, meta_chrom,
                    meta_strand, meta_tx_start, meta_tx_end, meta_core_start,
                )
                bc = np.bincount(Yb.reshape(-1), minlength=3)
                stats["label_counts"][split] = (np.array(stats["label_counts"][split]) + bc).tolist()
                stats["splits"][split] += int(Xb.shape[0])

    # Close writers
    for w in writers.values():
        w.close()

    # Save motif sanity stats
    if args.motif_sanity:
        stats["motif"]["donor"] = donor_motif_counts
        stats["motif"]["acceptor"] = acceptor_motif_counts

    stats_path = out_dir / "dataset_stats.json"
    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print(f"[OK] Dataset built in: {out_dir}")
    print(f"[OK] Wrote stats: {stats_path}")
    print("Split sample counts:", stats["splits"])
    if args.motif_sanity:
        print("Donor motif:", donor_motif_counts)
        print("Acceptor motif:", acceptor_motif_counts)


if __name__ == "__main__":
    main()
