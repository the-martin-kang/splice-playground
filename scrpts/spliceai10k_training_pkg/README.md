# SpliceAI 10k training package (low-RAM)

이 패키지는 **로컬(Mac)**에서 GRCh38 FASTA + annotation TSV(+ optional GTF/paralog)로
**SpliceAI-style 학습용 HDF5 데이터셋**을 만들고,
**Colab(H100)**에서 `spliceai-pytorch` 모델(10k)로 학습하는 최소 구성입니다.

## 0) 핵심 아이디어 (RAM 절약)

- 저장 포맷은 **one-hot**이 아니라:
  - `X`: uint8 code (A=0,C=1,G=2,T=3,N/other=4)
  - `Y`: uint8 class index (0=none, 1=acceptor, 2=donor)
- 학습 시에만 on-the-fly로 one-hot으로 변환합니다.
  - 디스크/업로드 용량을 4배 줄이고, 전처리 단계 RAM도 거의 안 씁니다.

---

## 1) 로컬에서 데이터셋 만들기

### 필요 파일
- `refannotation_with_canonical.tsv` (또는 `Mission6_refannotation.tsv`)
- `GRCh38.primary_assembly.genome.fa`
- (권장) GTF: transcript_id -> gene_id(ENSG) 매핑용
- (옵션) `paralog_gene.txt`: test set paralog gene 제거용 (ENSG list)

### 의존성
```bash
pip install numpy pyfaidx h5py tqdm
```

### 실행 예시
```bash
python build_spliceai_dataset.py \
  --annotation /path/to/refannotation_with_canonical.tsv \
  --fasta /path/to/GRCh38.primary_assembly.genome.fa \
  --out /path/to/out_spliceai10k_ds \
  --flank 10000 \
  --core-len 5000 \
  --test-chrs 1,3,5,7,9 \
  --val-frac 0.1 \
  --val-seed 42 \
  --motif-sanity
```

> 참고: 원본 SpliceAI/OpenSpliceAI 프로토콜은 **테스트만 chromosome-based(1,3,5,7,9 hold-out)** 로 두고,
> 나머지(training chromosomes)에서 **90:10 랜덤 split**로 train/val을 만듭니다.
> 이 스크립트도 그 방식을 따릅니다.

### paralog 제거까지 포함하려면
`paralog_gene.txt`는 ENSG list라서, annotation TSV의 transcript_id(ENST)에서
gene_id(ENSG)로 매핑이 필요합니다. 그래서 `--gtf`를 같이 넣습니다.

```bash
python build_spliceai_dataset.py \
  --annotation /path/to/refannotation_with_canonical.tsv \
  --fasta /path/to/GRCh38.primary_assembly.genome.fa \
  --gtf /path/to/gencode.vXX.annotation.gtf \
  --paralog /path/to/paralog_gene.txt \
  --out /path/to/out_spliceai10k_ds \
  --motif-sanity
```

---

## 2) Colab 학습

`colab_spliceai10k_train.ipynb` 노트북을 Colab에 올리고 실행하세요.

추천 흐름:
1) 로컬에서 만든 `out_spliceai10k_ds` 폴더를 tar.gz로 압축
2) Google Drive 업로드
3) Colab에서 Drive mount 후 `/content`로 복사 & 압축 해제
4) 학습 시작

---

## 3) 출력

- 데이터셋: `train_*.h5`, `val_*.h5`, `test_*.h5`
- 통계: `dataset_stats.json`
- 모델 체크포인트: notebook에서 `model_state_dict.pt`로 저장

