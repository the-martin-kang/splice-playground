#!/usr/bin/env python
"""
Preprocessing script to build SpliceAI-style train / val / test datasets
from a genome FASTA and GTF, and save them into a single HDF5 file.

Pipeline (roughly following SpliceAI paper):

1. GTF에서 protein_coding + canonical isoform만 추출 (gene_id, transcript_id 포함)
2. splice junction이 있는 transcript만 사용 (exon >= 2)
3. gene 단위로 chromosome 기반 train / test split:
      Train: chr2,4,8,10-22, X, Y
      Test : chr1,3,5,7,9
4. Test gene 중에서 BioMart로 얻은 paralog gene 리스트를 이용해 test에서 제거
5. 각 split에서 donor/acceptor 위치 → 윈도우 추출
6. train에서 10%를 랜덤으로 떼어 validation set 생성
7. HDF5 파일 하나에 다음 구조로 저장:
      /train/X  (N_train, L, 4)
      /train/Y  (N_train, 3, 2*DS)
      /val/X
      /val/Y
      /test/X
      /test/Y

X: one-hot DNA (A,C,G,T) → float32, shape (L, 4)
Y: multi-channel label → uint8, shape (3, 2*DS)
"""

import argparse
from collections import Counter
from functools import lru_cache
from pathlib import Path
import multiprocessing as mp

import numpy as np
import pandas as pd
from pyfaidx import Fasta
import h5py

# -----------------------------
# Default hyper-parameters
# -----------------------------

CL_DEFAULT = 5000   #몇개 예측할지 , Y = CL
DS_DEFAULT = 10000  # Context length, 하나 예측할때 context 몇개 사용??(좌우 합해서)
SEED_DEFAULT = 1337

# -----------------------------
# FASTA helpers
# -----------------------------

@lru_cache(maxsize=1)
def get_fa_idx(fa_path: str):
    """Cached pyfaidx Fasta object per process."""
    return Fasta(fa_path, as_raw=True, sequence_always_upper=True)


def _resolve_chrom_key(chrom: str, keys) -> str:
    """
    FASTA index에서 chrom 이름을 찾아준다.
    '1' / 'chr1' 사이를 자동으로 매핑해주는 안전장치.
    """
    if chrom in keys:
        return chrom
    if chrom.startswith("chr") and chrom[3:] in keys:
        return chrom[3:]
    prefixed = "chr" + chrom
    if prefixed in keys:
        return prefixed
    raise KeyError(
        f"Chromosome '{chrom}' not found in FASTA index. "
        f"Available examples: {list(keys)[:5]}"
    )


complement_dict = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A', 'N': 'N'}


def revcomp(seq: str) -> str:
    """Reverse-complement of a DNA sequence."""
    return ''.join(complement_dict.get(b, 'N') for b in reversed(seq))


def fetch_seq(fa_path: str, chrom: str, start: int, end: int, strand: str = '+') -> str:
    """
    Return uppercase sequence for 0-based half-open [start, end) on a given strand.
    """
    fa_idx = get_fa_idx(fa_path)
    key = _resolve_chrom_key(chrom, fa_idx.keys())
    rec = fa_idx[key]
    seq = rec[start:end]
    seq = seq.upper()
    if strand == '-':
        seq = revcomp(seq)
    return seq


# -----------------------------
# GTF → transcripts (exon list)
# -----------------------------

def extract_exons_from_gtf(gtf_path: str, targets):
    """
    Read GTF and extract canonical protein-coding exons for selected chromosomes.

    Returns:
        transcripts_dict:   {(chrom, strand, transcript_id): [[start,end], ...]}  (1-based inclusive)
        transcript_to_gene: {transcript_id: gene_id}
    """
    colnames = [
        "seqname","source","feature","start","end",
        "score","strand","frame","attribute"
    ]
    gtf_df = pd.read_csv(
        gtf_path,
        sep="\t",
        comment="#",
        names=colnames,
        dtype={"seqname": str},
    )

    print("Chromosome Types (seqname unique values):")
    print(gtf_df["seqname"].unique()[:30])
    print()

    def _attr_get(s, key):
        if not isinstance(s, str):
            return None
        parts = [p.strip() for p in s.split(";") if p.strip()]
        for p in parts:
            if p.startswith(key + " "):
                bits = p.split('"')
                if len(bits) >= 2:
                    return bits[1]
        return None

    # gene_type, transcript_id, gene_id 보강
    if "attribute" in gtf_df.columns:
        if "gene_type" not in gtf_df.columns:
            gtf_df["gene_type"] = gtf_df["attribute"].apply(
                lambda s: _attr_get(s, "gene_type") or _attr_get(s, "gene_biotype")
            )
        if "transcript_id" not in gtf_df.columns:
            gtf_df["transcript_id"] = gtf_df["attribute"].apply(
                lambda s: _attr_get(s, "transcript_id")
            )
        if "gene_id" not in gtf_df.columns:
            gtf_df["gene_id"] = gtf_df["attribute"].apply(
                lambda s: _attr_get(s, "gene_id")
            )

    # exon만 사용
    exons = gtf_df[gtf_df["feature"] == "exon"].copy()

    # canonical isoform만 (Ensembl_canonical 플래그)
    if "attribute" in exons.columns:
        exons = exons[exons["attribute"].str.contains("Ensembl_canonical", na=False)].copy()

    # protein_coding gene만
    gene_type_col = None
    if "gene_type" in exons.columns:
        gene_type_col = "gene_type"
    elif "gene_biotype" in exons.columns:
        gene_type_col = "gene_biotype"

    if gene_type_col is not None:
        exons = exons[exons[gene_type_col].fillna("") == "protein_coding"].copy()

    # 원하는 chromosome만 남기기
    exons = exons[exons["seqname"].astype(str).isin(targets)].copy()

    transcripts_dict = {}
    transcript_to_gene = {}

    # (chrom, strand, transcript_id, gene_id) 기준으로 그룹핑
    for (chrom, strand, tid, gid), grp in exons.groupby(
        ["seqname", "strand", "transcript_id", "gene_id"],
        dropna=True
    ):
        if tid is None or pd.isna(tid):
            continue
        ex = grp[["start","end"]].astype(int).values.tolist()
        ex.sort(key=lambda x: x[0])  # exon start 기준 정렬

        transcripts_dict[(str(chrom), str(strand), str(tid))] = ex

        # 버전 번호(.15 같은거) 제거해서 canonical gene id로 맞춰줌
        if gid is not None:
            gid_canonical = str(gid).split(".")[0]
        else:
            gid_canonical = None

        transcript_to_gene[str(tid)] = gid_canonical

    print(f"Extracted transcripts: {len(transcripts_dict)}")
    print(f"Unique genes (from these transcripts): {len(set(g for g in transcript_to_gene.values() if g is not None))}")
    return transcripts_dict, transcript_to_gene


# -----------------------------
# Exons → donor / acceptor label positions
# -----------------------------

def build_splice_labels_from_exons(transcripts):
    """
    Build donor / acceptor site maps from transcript exon coordinates.

    Inputs:
        transcripts: {(chrom, strand, tid): [[start,end], ...]} (1-based inclusive)

    Returns:
        donor_sites:    {(chrom,strand): [donor_pos,...]}    # 1-based positions
        acceptor_sites: {(chrom,strand): [acceptor_pos,...]} # 1-based positions
    """
    donor_sites, acceptor_sites = {}, {}
    for (chrom, strand, tid), exons in transcripts.items():
        exons_np = np.array(exons, dtype=int)
        if len(exons_np) < 2:
            # splice junction이 없는 경우는 건너뛰기
            continue

        if strand == "+":
            # Donor = exon end (except last exon)
            # Acceptor = exon start (except first exon)
            d_list = list(exons_np[:-1, 1])        # end of each exon except last
            a_list = list(exons_np[1:, 0])         # start of each exon except first
        elif strand == "-":
            # minus strand에서는 방향 반대라 좌표를 맞춰줌
            d_list = list(exons_np[1:, 0] - 1)     # start of exon (except first) - 1
            a_list = list(exons_np[:-1, 1] - 1)    # end of exon (except last) - 1
        else:
            continue

        key = (chrom, strand)
        donor_sites[key]    = sorted(set(donor_sites.get(key,    []) + d_list))
        acceptor_sites[key] = sorted(set(acceptor_sites.get(key, []) + a_list))

    return donor_sites, acceptor_sites


# -----------------------------
# Window extraction & labeling
# -----------------------------

def one_hot_encode(seq: str) -> np.ndarray:
    """Return array of shape (L,4) with channels A,C,G,T."""
    m = {'A':0, 'C':1, 'G':2, 'T':3}
    L = len(seq)
    X = np.zeros((L,4), dtype=np.float32)
    for i, ch in enumerate(seq.upper()):
        j = m.get(ch)
        if j is not None:
            X[i, j] = 1.0
    return X


def label_vector(center_pos_1b, donor_list, acceptor_list, CL: int):
    """
    중심 위치(center_pos_1b)를 기준으로 길이 CL짜리 label 벡터 생성.

    반환 shape: (CL, 3)
      [:,0] = non-splice
      [:,1] = donor
      [:,2] = acceptor
    """
    half = CL // 2
    y = np.zeros((CL, 3), dtype=np.uint8)

    # donor
    for p in donor_list:
        d = p - center_pos_1b  # 1-based 좌표 차이
        if -half <= d < half:
            idx = d + half
            y[idx, 1] = 1

    # acceptor
    for p in acceptor_list:
        d = p - center_pos_1b
        if -half <= d < half:
            idx = d + half
            y[idx, 2] = 1

    # non-splice = 둘 다 아닌 곳
    non_mask = (y[:, 1] == 0) & (y[:, 2] == 0)
    y[non_mask, 0] = 1

    return y  # (CL, 3)


def extract_window_idx(fasta_path, chrom, center_pos_0b, strand='+', CL=CL_DEFAULT, DS=DS_DEFAULT):
    """
    SpliceAI-10k 스타일 윈도우 추출.

    - CL: label block 길이 (예: 5000)
    - DS: window size S (예: 10000)

    한 샘플의 입력 길이 = CL + DS = 15000
    """
    half = (CL + DS) // 2

    start = max(0, center_pos_0b - half)
    end   = center_pos_0b + half

    # ✅ fasta_path까지 함께 전달
    seq = fetch_seq(fasta_path, chrom, start, end, strand=strand)

    # 왼쪽 패딩
    left_pad = half - (center_pos_0b - start)
    if left_pad > 0:
        seq = 'N' * left_pad + seq

    # 오른쪽 패딩
    want_len = CL + DS
    if len(seq) < want_len:
        seq = seq + 'N' * (want_len - len(seq))

    # 혹시 더 길게 들어오면 잘라줌
    return seq[:want_len]


def get_sequences_and_labels(
    fasta_path,
    chrom,
    strand,
    positions,
    donor_sites,
    acceptor_sites,
    CL: int,
    DS: int,
):
    X_list, Y_list = [], []
    motif_donor, motif_acceptor = Counter(), Counter()

    key = (chrom, strand)
    donors    = donor_sites.get(key, [])
    acceptors = acceptor_sites.get(key, [])

    for pos in positions:
        center_pos_1b = int(pos)
        center_pos_0b = center_pos_1b - 1

        seq = extract_window_idx(
            fasta_path,
            chrom,
            center_pos_0b,
            strand=strand,
            CL=CL,
            DS=DS,
        )
        X_oh = one_hot_encode(seq)    # (CL+DS, 4)

        # ⬇️ 여기서 (CL, 3) 반환
        y = label_vector(
            center_pos_1b,
            donors,
            acceptors,
            CL=CL,
        )

        X_list.append(X_oh)
        Y_list.append(y)

        # motif_* 업데이트 부분은 그대로 두면 됨
        # motif_donor.update(...)
        # motif_acceptor.update(...)

    return X_list, Y_list, motif_donor, motif_acceptor

# -----------------------------
# Chromosome splits & positions
# -----------------------------

TRAIN_NUMS = [2, 4, 8] + list(range(10, 23))  # 2,4,8,10-22
TEST_NUMS  = [1, 3, 5, 7, 9]

CHROM_SPLITS = {
    "train": (
        {str(i) for i in TRAIN_NUMS} |
        {f"chr{i}" for i in TRAIN_NUMS} |
        {"X", "Y", "chrX", "chrY"}
    ),
    "test": (
        {str(i) for i in TEST_NUMS} |
        {f"chr{i}" for i in TEST_NUMS}
    ),
}


def sample_positions(donor_sites, acceptor_sites):
    """
    donor_sites, acceptor_sites 에 들어 있는 splice 관련 위치를
    (chrom, strand) 별로 합친 dict를 만든다.

    max_per_chrom 제한 없이, 각 (chrom, strand)의 donor + acceptor 위치를 전부 사용.
    """
    pos_map = {}
    all_keys = set(list(donor_sites.keys()) + list(acceptor_sites.keys()))
    for key in all_keys:
        donors = set(donor_sites.get(key, []))
        acceptors = set(acceptor_sites.get(key, []))
        all_pos = sorted(donors.union(acceptors))
        pos_map[key] = all_pos
    return pos_map


# -----------------------------
# Paralogs (BioMart 리스트)
# -----------------------------

# -----------------------------
# Paralogs (BioMart 리스트)
# -----------------------------

def load_paralog_gene_ids(path: str | None):
    """
    Ensembl BioMart에서 export한 'paralog가 존재하는 gene' 리스트 파일을 읽는다.

    기대 포맷(예시, 헤더가 있어도 상관 없음):
        Gene stable ID
        ENSG00000123456
        ENSG00000234567
        ...

    - 공백/빈 줄은 무시
    - 'ENSG'로 시작하지 않는 줄(헤더, 카운트 등)은 무시
    - gene 버전 번호(ENSG00000123456.15)는 잘라서 canonical ID로 저장
    """
    if path is None:
        print("No test-paralog-list provided; NOT removing paralogs from test set.")
        return None

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Paralog gene list file not found: {p}")

    paralogs: set[str] = set()
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # 헤더나 카운트 같은 줄은 건너뜀
            if not line.startswith("ENSG"):
                continue
            # 첫 컬럼만 사용, 버전 제거
            gid = line.split()[0].split(".")[0]
            paralogs.add(gid)

    print(f"Loaded {len(paralogs)} paralog gene IDs (canonical) from {p}")
    return paralogs


# -----------------------------
# Gene-level split + paralog removal
# -----------------------------

def split_transcripts_by_chrom_and_paralog(
    transcripts_dict,
    transcript_to_gene,
    paralog_genes_for_test=None,
):
    """
    1) chromosome 기준으로 train / test gene을 나누고
    2) test 쪽에서 paralog가 있는 gene들은 제거한다.

    Returns:
        train_transcripts: {(chrom,strand,tid): exons}
        test_transcripts:  {(chrom,strand,tid): exons}

    그리고 내부에서 train/test donor-acceptor pair 수를 출력한다.
    """

    train_transcripts = {}
    test_transcripts = {}

    test_gene_ids_before = set()
    test_gene_ids_after = set()

    # transcript별로 어느 split에 속하는지 결정
    for (chrom, strand, tid), exons in transcripts_dict.items():
        chrom_key = str(chrom)
        gid = transcript_to_gene.get(str(tid))

        if chrom_key in CHROM_SPLITS["train"]:
            train_transcripts[(chrom, strand, tid)] = exons

        elif chrom_key in CHROM_SPLITS["test"]:
            if gid:
                test_gene_ids_before.add(gid)
                # paralog gene이면 test에서 제거
                if paralog_genes_for_test and gid in paralog_genes_for_test:
                    continue
                test_gene_ids_after.add(gid)
            test_transcripts[(chrom, strand, tid)] = exons

    # donor-acceptor pair 수 세는 헬퍼
    def _count_pairs(transcripts):
        pairs = 0
        genes = set()
        for (chrom, strand, tid), exons in transcripts.items():
            L = len(exons)
            if L > 1:
                # exon n개 → splice junction (donor-acceptor pair) = n-1개
                pairs += (L - 1)
            gid = transcript_to_gene.get(str(tid))
            if gid:
                genes.add(gid)
        return pairs, len(genes)

    train_pairs, n_train_genes = _count_pairs(train_transcripts)
    test_pairs,  n_test_genes  = _count_pairs(test_transcripts)

    print("=== Gene / donor-acceptor pair counts (before val split) ===")
    print(f"Train genes: {n_train_genes}, donor-acceptor pairs: {train_pairs}")
    if paralog_genes_for_test is not None:
        print(f"Test genes before paralog removal: {len(test_gene_ids_before)}")
    print(f"Test genes after paralog removal:  {n_test_genes}, donor-acceptor pairs: {test_pairs}")
    print("================================================================")

    return train_transcripts, test_transcripts


# -----------------------------
# Multiprocessing worker
# -----------------------------

def _process_chrom_strand(args):
    """
    Worker for a single (chrom, strand).
    args: (fasta_path, chrom, strand, positions, donor_sites, acceptor_sites, CL, DS)
    """
    fasta_path, chrom, strand, positions, donor_sites, acceptor_sites, CL, DS = args
    X, Y, md, ma = get_sequences_and_labels(
        fasta_path=fasta_path,
        chrom=chrom,
        strand=strand,
        positions=positions,
        donor_sites=donor_sites,
        acceptor_sites=acceptor_sites,
        CL=CL,
        DS=DS,
    )
    return X, Y, md, ma


def create_dataset_per_split_mp(
    fasta_path: str,
    train_transcripts,
    test_transcripts,
    CL: int,
    DS: int,
    num_workers: int = None,
):
    """
    Build train / test datasets with multiprocessing, using 이미 split된 transcripts.

    Returns:
        (X_train, Y_train, md_train, ma_train),
        (X_test,  Y_test,  md_test,  ma_test)
    """
    if num_workers is None or num_workers <= 0:
        num_workers = max(1, mp.cpu_count() - 1)

    results = {}

    for split_name, transcripts in (("train", train_transcripts), ("test", test_transcripts)):
        # 1) 이 split에 속한 transcript들로부터 donor/acceptor 위치 생성
        donor_sites, acceptor_sites = build_splice_labels_from_exons(transcripts)

        # 2) (chrom,strand)별로 사용할 position 모으기
        pos_map = sample_positions(donor_sites, acceptor_sites)

        # 3) 멀티프로세싱 task 리스트 준비
        tasks = [
            (fasta_path, chrom, strand, positions, donor_sites, acceptor_sites, CL, DS)
            for (chrom, strand), positions in pos_map.items()
        ]

        X_all, Y_all = [], []
        motif_donor, motif_acceptor = Counter(), Counter()

        print(f"[{split_name}] #chrom,strand groups = {len(tasks)/2}, using {num_workers} workers")

        with mp.Pool(processes=num_workers) as pool:
            for X, Y, md, ma in pool.imap_unordered(_process_chrom_strand, tasks):
                X_all.extend(X)
                Y_all.extend(Y)
                motif_donor.update(md)
                motif_acceptor.update(ma)

        results[split_name] = (X_all, Y_all, motif_donor, motif_acceptor)

    return results["train"], results["test"]


# -----------------------------
# Saving / train-val split (HDF5)
# -----------------------------

def train_val_split(X_list, Y_list, val_frac: float, seed: int):
    """Randomly split X/Y lists into train/val according to val_frac."""
    rng = np.random.default_rng(seed)
    n_total = len(X_list)
    n_val = int(n_total * val_frac)
    indices = np.arange(n_total)
    rng.shuffle(indices)
    val_idx = indices[:n_val]
    train_idx = indices[n_val:]

    X_train = [X_list[i] for i in train_idx]
    Y_train = [Y_list[i] for i in train_idx]
    X_val   = [X_list[i] for i in val_idx]
    Y_val   = [Y_list[i] for i in val_idx]

    return X_train, Y_train, X_val, Y_val


def save_to_hdf5(
    h5_path: Path,
    X_train, Y_train,
    X_val,   Y_val,
    X_test,  Y_test,
    CL: int,
    DS: int,
    chunk_size_hint: int = 10000,
):
    """
    Save train/val/test into a single HDF5 file with groups:
        /train/X, /train/Y
        /val/X,   /val/Y
        /test/X,  /test/Y

    HDF5 dataset chunk size는 각 split에서 min(chunk_size_hint, N) 로 설정.
    학습할 때는 h5["train/X"][i:j] 식으로 2만 샘플씩 슬라이스해서 쓰면 됨.
    """
    h5_path = Path(h5_path)
    h5_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing HDF5 to: {h5_path}")

    with h5py.File(h5_path, "w") as f:
        f.attrs["CL"] = CL
        f.attrs["DS"] = DS

        def _write_group(name, X_list, Y_list):
            X_arr = np.stack(X_list, axis=0)
            Y_arr = np.stack(Y_list, axis=0)

            N = X_arr.shape[0]
            if N == 0:
                print(f"[WARN] Group {name} has 0 samples, skipping.")
                return

            cs = min(chunk_size_hint, N)

            g = f.create_group(name)
            dset_X = g.create_dataset(
                "X",
                data=X_arr,
                compression="gzip",
                chunks=(cs,) + X_arr.shape[1:],
            )
            dset_Y = g.create_dataset(
                "Y",
                data=Y_arr,
                compression="gzip",
                chunks=(cs,) + Y_arr.shape[1:],
            )
            print(f"  Group '{name}': X shape={dset_X.shape}, Y shape={dset_Y.shape}, chunk_size={cs}")

        _write_group("train", X_train, Y_train)
        _write_group("val",   X_val,   Y_val)
        _write_group("test",  X_test,  Y_test)

    print("HDF5 write complete.")


# -----------------------------
# GTF chromosome targets
# -----------------------------

def build_targets_for_gtf():
    """
    Build chromosome targets for GTF filtering.
    Supports both Ensembl style ('1') and UCSC style ('chr1').
    """
    nums = list(range(1, 23))
    targets = {str(i) for i in nums} | {f"chr{i}" for i in nums} | {"X", "Y", "chrX", "chrY"}
    return targets


# -----------------------------
# Main
# -----------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Preprocess genome/GTF into SpliceAI-style datasets and save to HDF5."
    )

    # ✅ 한 번에 처리할 공용 디렉터리
    parser.add_argument(
        "--data-dir",
        required=True,
        help=(
            "FASTA, GTF, paralog_gene.txt가 모두 들어 있는 디렉터리. "
            "HDF5 출력도 여기에 생성됨."
        ),
    )

    # ✅ 파일 이름은 기본값을 이렇게 두고, 필요하면 옵션으로 바꿀 수 있게
    parser.add_argument(
        "--fasta-name",
        type=str,
        default="GRCh38.primary_assembly.genome.fa",
        help="data-dir 안에 있는 FASTA 파일 이름 (기본: GRCh38.primary_assembly.genome.fa)",
    )
    parser.add_argument(
        "--gtf-name",
        type=str,
        default="gencode.v46.primary_assembly.annotation.gtf",
        help="data-dir 안에 있는 GTF 파일 이름 (기본: gencode.v46.primary_assembly.annotation.gtf)",
    )
    parser.add_argument(
        "--paralog-name",
        type=str,
        default="paralog_gene.txt",
        help="data-dir 안에 있는 paralog gene 리스트 파일 이름 (기본: paralog_gene.txt)",
    )
    parser.add_argument(
        "--outname",
        type=str,
        default="splice_data.h5",
        help="출력 HDF5 파일 이름 (기본: splice_data.h5)",
    )

    # 나머지 하이퍼파라미터들은 그대로 둠
    parser.add_argument("--cl", type=int, default=CL_DEFAULT, help=f"Center length CL (default {CL_DEFAULT}).")
    parser.add_argument("--ds", type=int, default=DS_DEFAULT, help=f"Label half-window DS (default {DS_DEFAULT}).")
    parser.add_argument("--val-frac", type=float, default=0.1, help="Validation fraction from train (default 0.1).")
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT, help=f"Random seed for val split (default {SEED_DEFAULT}).")
    parser.add_argument("--workers", type=int, default=0, help="Number of worker processes (0 = cpu_count-1).")

    args = parser.parse_args()

    base_dir = Path(args.data_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    # ✅ 여기서 한 번에 경로를 정리
    fasta_path = base_dir / args.fasta_name
    gtf_path = base_dir / args.gtf_name
    outdir = base_dir
    h5_path = outdir / args.outname

    # paralog liste 파일 경로 (없으면 None)
    paralog_list_path = base_dir / args.paralog_name
    if paralog_list_path.exists():
        test_paralog_list_str = str(paralog_list_path)
    else:
        test_paralog_list_str = None
        print(f"[WARN] Paralog gene list file not found at {paralog_list_path}, "
              "proceeding WITHOUT paralog removal for test set.")

    CL = args.cl
    DS = args.ds

    print("=== Settings ===")
    print(f"data-dir:   {base_dir}")
    print(f"FASTA:      {fasta_path}")
    print(f"GTF:        {gtf_path}")
    print(f"Output dir: {outdir}")
    print(f"HDF5 file:  {h5_path}")
    print(f"CL:         {CL}")
    print(f"DS:         {DS}")
    print(f"val_frac:   {args.val_frac}")
    print(f"seed:       {args.seed}")
    print(f"workers:    {args.workers if args.workers > 0 else max(1, mp.cpu_count()-1)}")
    print(f"paralog list for test: {test_paralog_list_str}")
    print()

    # 1) Extract exons + transcript→gene 매핑
    targets = build_targets_for_gtf()
    transcripts_dict, transcript_to_gene = extract_exons_from_gtf(str(gtf_path), targets)

    # 2) BioMart에서 뽑아온 paralog gene 리스트 로드 (옵션)
    paralog_genes_for_test = load_paralog_gene_ids(test_paralog_list_str)

    # 3) chromosome 기준 + paralog 제거 기준으로 train/test transcript split
    train_transcripts, test_transcripts = split_transcripts_by_chrom_and_paralog(
        transcripts_dict,
        transcript_to_gene,
        paralog_genes_for_test=paralog_genes_for_test,
    )

    # 4) 멀티프로세싱으로 train/test 데이터 생성 (X_list / Y_list)
    (X_train_all, Y_train_all, md_train, ma_train), \
    (X_test,      Y_test,      md_test,  ma_test) = create_dataset_per_split_mp(
        fasta_path=str(fasta_path),
        train_transcripts=train_transcripts,
        test_transcripts=test_transcripts,
        CL=CL,
        DS=DS,
        num_workers=args.workers,
    )

    print(f"Total train positions (before val split): {len(X_train_all)}")
    print(f"Total test  positions: {len(X_test)}")

    # 5) train → train/val split
    X_train, Y_train, X_val, Y_val = train_val_split(
        X_train_all, Y_train_all, val_frac=args.val_frac, seed=args.seed
    )

    print(f"Final train: {len(X_train)}, val: {len(X_val)}, test: {len(X_test)}")

    # 6) HDF5로 저장
    save_to_hdf5(
        h5_path=h5_path,
        X_train=X_train, Y_train=Y_train,
        X_val=X_val,     Y_val=Y_val,
        X_test=X_test,   Y_test=Y_test,
        CL=CL,
        DS=DS,
        chunk_size_hint=10000,
    )

if __name__ == "__main__":
    # Important for multiprocessing on Windows / macOS
    mp.freeze_support()
    main()