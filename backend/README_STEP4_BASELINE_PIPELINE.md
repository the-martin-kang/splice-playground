# STEP4 baseline protein / structure pipeline

이 패치는 STEP4 baseline의 **엄격한 sequence + structure provenance 파이프라인**을 추가합니다.

## 추가된 것

- `protein_reference` 테이블
  - canonical mRNA / CDS / protein sequence 저장
  - RefSeq / Ensembl / UniProt cross-check 결과 저장
  - DB exon→mRNA→CDS→protein 재검증 결과 저장

- `protein_structure_asset` 테이블
  - experimental PDB / predicted AlphaFoldDB 구조 asset 메타데이터 저장
  - Supabase Storage object path / signed URL 제공용 메타데이터 저장

- 새 API
  - `GET /api/diseases/{disease_id}/step4-baseline`
  - `GET /api/states/{state_id}/step4-baseline`

- 새 스크립트
  - `scripts/ingest_step4_baseline.py`
  - `scripts/validate_step4_baseline.py`

## 소스 우선순위

1. **Transcript authority**: gene table의 canonical transcript + Ensembl/MANE lookup
2. **Protein authority**: translated CDS
3. **Cross-check**
   - Ensembl protein translation exact match
   - RefSeq protein exact match
   - UniProt sequence exact match
4. **Structure authority**
   - PDBe/RCSB experimental structures first
   - AlphaFoldDB full-length predicted structure fallback

## Supabase SQL 적용

먼저 아래 SQL을 Supabase SQL editor에서 실행:

- `supabase/sql/2026-03-13_step4_baseline.sql`

## 환경변수

추가 권장값:

```bash
STEP4_STRUCTURE_BUCKET=structure-assets
NCBI_TOOL=splice-playground
NCBI_EMAIL=your_email@example.com
NCBI_API_KEY=...               # optional, but recommended for faster NCBI access
HTTP_USER_AGENT="splice-playground/0.1 (+step4-baseline)"
```

## Ingest 예시

visible disease에 연결된 gene들을 자동으로 처리:

```bash
python scripts/ingest_step4_baseline.py
```

특정 gene만 처리:

```bash
python scripts/ingest_step4_baseline.py --gene-id BRCA1
```

특정 disease case 기준으로 처리:

```bash
python scripts/ingest_step4_baseline.py --disease-id brca1_case
```

dry-run:

```bash
python scripts/ingest_step4_baseline.py --gene-id BRCA1 --dry-run
```

## 재검증

DB의 canonical exon sequence를 이어붙여 만든 mRNA가 저장된 baseline protein과 맞는지 다시 확인:

```bash
python scripts/validate_step4_baseline.py --gene-id BRCA1
```

write-back:

```bash
python scripts/validate_step4_baseline.py --gene-id BRCA1 --write-back
```

## 프론트 연동 포인트

`/step4-baseline` 응답에는:

- baseline protein metadata
- validation status / report
- structure asset signed URLs
- default structure asset id

가 들어 있으므로, 프론트는 이 JSON만으로 STEP4 baseline viewer를 붙일 수 있습니다.

## publication-grade 운영 원칙

- UniProt exact match가 안 되면 **자동 구조 ingest를 중단**하고 manual review로 보냅니다.
- DB exon→mRNA→protein validation이 실패하면 `validation_status=review_required`로 남깁니다.
- 구조 파일은 storage에, provenance는 DB JSONB에 남깁니다.
- experimental structure와 predicted structure를 섞어 쓰되, default 선택은 coverage/resolution을 반영합니다.
