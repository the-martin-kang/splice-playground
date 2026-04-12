# PATCH_NOTES_STEP4_STATEFUL_2TRACK_2026-03-14

이번 패치는 STEP4를 **2-track(normal / user)** 으로 실제 backend에서 다루기 위한 상태 기반 API와 비동기 구조 예측 job 골격을 추가합니다.

## 핵심 추가점

### 1) STEP4 stateful API 추가
- `GET /api/states/{state_id}/step4`
  - normal track: Supabase에 저장된 canonical protein / baseline structures
  - user track: state 기반 current transcript / cDNA / CDS / protein / translation sanity / structure job 상태
- `POST /api/states/{state_id}/step4/jobs`
  - provider 기본값: `colabfold`
  - user protein이 normal protein과 완전히 같으면 `baseline_reuse` succeeded job 생성 가능
  - 동일 protein sha + provider 조합 job dedupe
- `GET /api/step4-jobs/{job_id}`
  - 구조 job 상태 / asset signed URL / 비교 payload 반환

### 2) STEP4 transcript → protein 재구성
- STEP3 primary event를 이용해 STEP4용 predicted transcript를 재구성
- 현재 지원/대응 방식
  - `EXON_EXCLUSION`
  - `PSEUDO_EXON`
  - `BOUNDARY_SHIFT`
  - `CANONICAL_STRENGTHENING`
  - `NONE`
  - `COMPLEX`는 canonical transcript fallback + warning
- canonical exon block + pseudo exon / boundary shift block을 `predicted_transcript.blocks` 로 반환

### 3) translation sanity 계산 강화
- canonical baseline CDS start를 canonical exon mapping으로 gene0에 역투영
- user transcript에서 같은 시작점이 살아 있는지 확인
- preserved start codon 기준으로 user CDS / protein 생성
- 반환 필드
  - `start_codon_preserved`
  - `stop_codon_found`
  - `multiple_of_three`
  - `frameshift_likely`
  - `premature_stop_likely`
  - `internal_stop_positions_aa`
  - `protein_length`

### 4) normal vs user protein 비교
- exact match 여부
- first mismatch AA 위치
- 길이 변화
- normalized edit similarity(Levenshtein 기반)
- user protein이 normal과 동일하면 baseline structure 재사용 가능 여부 계산

### 5) structure job / worker 골격 추가
- repository: `app/db/repositories/structure_job_repo.py`
- worker script: `scripts/run_step4_jobs.py`
- provider: 현재 `colabfold` queue/worker 경로 구현
- App Runner 본체는 job 생성/조회만 담당, 실제 구조 예측은 별도 worker가 수행하도록 설계
- worker는 ColabFold output(`.pdb/.cif/.json`)을 Supabase storage에 업로드하고 job row를 업데이트
- optional structural alignment binary(`STEP4_ALIGNMENT_BIN`)가 있으면 baseline default 구조와 비교 payload 저장

## 수정된 주요 파일
- `app/schemas/step4.py`
- `app/api/routes/step4.py`
- `app/core/config.py`
- `app/db/repositories/region_repo.py`
- `app/db/repositories/structure_job_repo.py` (new)
- `app/services/protein_translation.py`
- `app/services/step4_state_service.py` (new)
- `app/services/structure_job_service.py` (new)
- `app/services/storage_service.py`
- `scripts/run_step4_jobs.py` (new)

## 새 env 키
- `COLABFOLD_BATCH_CMD` (default: `colabfold_batch`)
- `COLABFOLD_EXTRA_ARGS`
- `STEP4_JOB_WORKDIR` (default: `/tmp/step4_jobs`)
- `STEP4_JOB_TIMEOUT_SECONDS` (default: `21600`)
- `STEP4_ALIGNMENT_BIN`

## 참고
- 현재 STEP4 user-track transcript reconstruction은 **STEP3 primary event 1개** 를 기준으로 동작합니다.
- `COMPLEX` event는 보수적으로 canonical transcript fallback 입니다.
- baseline 구조 재사용 경로(`baseline_reuse`)는 user protein이 normal protein과 완전히 동일할 때만 자동 허용합니다.
- ColabFold worker는 실제 실행 환경(GPU / binary / weights / databases)에 따라 운영 환경 세팅이 별도로 필요합니다.
