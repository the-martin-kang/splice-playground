# STEP4 baseline overlay patch (2026-03-13)

이 패치는 STEP4 baseline의 **protein sequence / structure provenance 파이프라인**과 **프론트가 바로 읽을 수 있는 baseline API**를 추가합니다.

## 핵심 추가 사항

- 새 API
  - `GET /api/diseases/{disease_id}/step4-baseline`
  - `GET /api/states/{state_id}/step4-baseline`

- 새 테이블 / bucket SQL
  - `supabase/sql/2026-03-13_step4_baseline.sql`
  - `protein_reference`
  - `protein_structure_asset`
  - `structure-assets` bucket

- 새 서비스 / 스키마
  - `app/services/protein_translation.py`
  - `app/services/step4_sources.py`
  - `app/services/step4_validation.py`
  - `app/services/step4_baseline_service.py`
  - `app/schemas/step4.py`
  - `app/db/repositories/step4_baseline_repo.py`
  - `app/api/routes/step4.py`

- 새 ingestion / validation 스크립트
  - `scripts/ingest_step4_baseline.py`
  - `scripts/validate_step4_baseline.py`

## 설계 원칙

- transcript authority: gene table canonical transcript + Ensembl/MANE
- protein cross-check: translated CDS vs Ensembl protein / RefSeq protein / UniProt
- 구조 우선순위: PDBe/RCSB experimental first, AlphaFoldDB fallback
- UniProt exact match 실패 시 자동 structure ingest 중단
- DB exon → canonical mRNA → CDS → protein 재검증 결과를 validation JSON에 저장

## 적용 순서

1. Supabase SQL editor에서 `supabase/sql/2026-03-13_step4_baseline.sql` 실행
2. 필요하면 env 추가
   - `STEP4_STRUCTURE_BUCKET=structure-assets`
   - `NCBI_EMAIL=...`
   - `NCBI_API_KEY=...` (optional)
3. baseline ingest 실행
   - `python scripts/ingest_step4_baseline.py --gene-id BRCA1`
4. 재검증
   - `python scripts/validate_step4_baseline.py --gene-id BRCA1`
5. AWS backend 재배포

## 주의사항

- 이 컨테이너에서는 외부 인터넷 호출을 실제 실행해 보지 못했기 때문에,
  external API 연동 부분은 **문법 검증/정적 점검 중심**으로 작성되었습니다.
- `python -m compileall app scripts` 기준 문법은 통과했습니다.
- PDBe / AlphaFold API 스키마가 바뀌면 `app/services/step4_sources.py`의 파서를 먼저 확인하세요.
