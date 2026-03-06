# Mission6 Validation Package (splice-playground)

이 폴더는 `splice-playground`에서 **Mission6 스타일의 검증 파이프라인**을 재현하기 위한 작은 Python 패키지입니다.

- 4000bp input window (Mission6 baseline)
- gene-outside masking with `N` (one-hot zeros)
- negative strand off-by-one 보정
- ref/alt는 **positive strand 기준**으로 제공 (Mission6 컨벤션)


## 1) Mission6 (window=4000) 빠른 검증

```bash
# (backend 폴더에서 실행한다고 가정)
export PYTHONPATH=$PWD:$PYTHONPATH

python -m validation_pkg.validation.mission6.validate_backend \
  --selected path/to/selected_gene.tsv \
  --annotation path/to/Mission6_refannotation.tsv \
  --fasta path/to/GRCh38.primary_assembly.genome.fa \
  --model path/to/mission5.pt \
  --backend-url http://localhost:8000 \
  --out report_vs_backend.json
```

backend는 아래 endpoint가 있어야 합니다.
- `GET /api/diseases`
- `GET /api/diseases/{disease_id}/window?window_size=4000`


---

## 2) SpliceAI-10k (window=15000 → core=5000) 기존 방식

이미 사용 중인 방식(선택 gene TSV + annotation/FASTA로 local window 구성 후, backend window와 비교 + plot)입니다.

### JSON 리포트

```bash
python -m validation_pkg.validation.spliceai10k.validate_backend \
  --selected path/to/selected_gene.tsv \
  --annotation path/to/refannotation_with_canonical.tsv \
  --fasta path/to/GRCh38.primary_assembly.genome.fa \
  --model path/to/spliceai10k_checkpoint.pt \
  --backend-url http://localhost:8000 \
  --window-size 15000 \
  --out-len 5000 \
  --out report_spliceai10k_vs_backend.json
```

### Plot (Mission6 스타일)

```bash
python -m validation_pkg.validation.spliceai10k.visualize_backend \
  --selected path/to/selected_gene.tsv \
  --annotation path/to/refannotation_with_canonical.tsv \
  --fasta path/to/GRCh38.primary_assembly.genome.fa \
  --model path/to/spliceai10k_checkpoint.pt \
  --backend-url http://localhost:8000 \
  --window-size 15000 \
  --out-len 5000 \
  --out-dir plots_spliceai10k
```

> 주의: 이 패키지는 **`spliceai-pytorch` 모듈을 import 하지 않습니다.**


---

## 3) (NEW) Supabase(DB) canonical splice site 전체 검증

너가 원한 방식:

- **top-k peak**를 보지 않고,
- **Supabase(region 테이블)**에 올라간 canonical exon boundary에서 유도되는
  모든 내부 splice site들(`exon2_acceptor` ... `exon{n-1}_donor`)을
- **전체 gene(pre-mRNA) 길이 전체**에 대해 한 번에 평가합니다.

라벨 컨벤션은 너가 말한 그대로를 따릅니다.

- acceptor label = exon start index
- donor label = exon end index
- transcript 시작/끝은 제외 (exon1 acceptor, last exon donor)

### 실행

```bash
python -m validation_pkg.validation.spliceai10k.canonical_eval_backend \
  --backend-url http://localhost:8000 \
  --model path/to/spliceai_window=10000.pt \
  --flank 10000 \
  --allow-gap-pad \
  --out report_canonical_sites.json
```

옵션:
- `--disease-id <id>`: 한 개만
- `--flank 10000`: (학습 시 total flank) = 10000이면 좌/우 5000 padding
- `--allow-gap-pad`: region이 start=0이 아니거나 중간에 gap이 있는 경우 `N`으로 채움(권장)

출력에는 각 canonical site별로:
- `kind` (`exon10_donor` 같은 형태)
- `pos_gene0`
- `motif` / `motif_ok` (acceptor: `AG`, donor: `GT`/`GC`)
- `prob`, `rank`, `percentile`


---

## 4) (NEW) SNV 변화는 DB canonical marker를 얹어서 gene0 축으로 시각화

window 기반(예: 15000→5000 core)으로 ref/alt 트랙을 그리면서,
동시에 **DB exon boundary 기반 canonical site들을 marker로 찍습니다.**

```bash
python -m validation_pkg.validation.spliceai10k.visualize_snv_backend_gene0 \
  --backend-url http://localhost:8000 \
  --model path/to/spliceai_window=10000.pt \
  --window-size 15000 \
  --out-len 5000 \
  --label \
  --out-dir plots_spliceai10k_gene0
```

`index.html`이 생성됩니다.


---

## 3) (NEW) DB canonical 기준 "전체 gene" splice site 점수 검증 + 서열 일치(FASTA) 검증

요구사항 정리:
1) **DB region sequence가 FASTA/annotation 기준으로 맞게 올라갔는지** (서열 1:1 검증; DB의 'N' 패딩 구간은 마스킹 처리)
2) **DB canonical exon 경계(= splice junction 라벨 기준)** 에서 donor/acceptor 확률이 잘 나오는지
3) transcript boundary는 라벨에서 항상 제외(exon1 acceptor, last exon donor)

```bash
python -m validation_pkg.validation.spliceai10k.canonical_eval_backend \
  --backend-url http://localhost:8000 \
  --annotation path/to/refannotation_with_canonical.tsv \
  --fasta path/to/GRCh38.primary_assembly.genome.fa \
  --model path/to/spliceai_window=10000.pt \
  --out report_db_canonical_fullgene.json \
  --orf-sanity
```

- 기본값은 **DB region 사이 gap을 'N'으로 패딩**(MSH2처럼 exon1이 gene0=0에서 시작하지 않는 케이스를 위해).
- gap이 있으면 실패시키고 싶으면 `--strict-contiguous` 옵션을 켜세요.

backend가 아래 endpoint를 지원해야 합니다.
- `GET /api/diseases/{disease_id}`  (Step2 payload)
- `GET /api/diseases/{disease_id}/regions/{region_type}/{region_number}?include_sequence=true`

---

## 4) (NEW) disease_id (gene0) 기준 SNV window를 mission6 스타일로 plot

`/window?window_size=15000`에서 받은 ref/alt 서열을 모델에 넣고,
output core(5000)에서 ref vs alt 확률곡선을 **mission6 plot 스타일**로 시각화합니다.

```bash
python -m validation_pkg.validation.spliceai10k.visualize_snv_backend_gene0_mission6style \
  --backend-url http://localhost:8000 \
  --annotation path/to/refannotation_with_canonical.tsv \
  --model path/to/spliceai_window=10000.pt \
  --window-size 15000 \
  --out-len 5000 \
  --out-dir plots_backend_spliceai10k
```
