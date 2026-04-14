# PATCH NOTES — G5 STEP4 worker ready (2026-04-12)

가정:
- public API는 기존 `t3.small` EC2가 계속 담당
- `g5.xlarge` EC2는 **worker-only** 호스트로 사용
- frontend / dev_gui / public API traffic은 계속 `api.splice-playground-api.com` 으로 들어감

## 이번 패치 핵심

### 1) STEP4 worker 신뢰성 강화
- `structure_job` atomic claim 로직 추가 (`claim_job_if_queued`)
- 여러 worker / 재시작 상황에서도 같은 queued job을 중복 실행할 가능성을 줄임
- worker token (`hostname:pid`) 를 `external_job_id` 로 남김

### 2) ColabFold 산출물 정리 개선
- output 구조 파일 중 **default structure** 를 ranking 기반으로 선택
  - `rank_001` 우선
  - 없으면 `ranking_debug.json.order` 를 참조
  - 그래도 없으면 구조 파일 중 첫 후보 선택
- input FASTA / stdout.log / stderr.log 도 Storage에 함께 업로드
- `result_payload` 에 default structure 이름과 worker metadata 저장

### 3) STEP4 job 응답 개선
- `Step4StructureJobPublic` 에 추가:
  - `default_structure_asset`
  - `molstar_default`
- frontend / dev_gui 가 job 완료 후 바로 Mol* 로 예측 구조를 띄우기 쉬워짐

### 4) GPU 전환 운영 문구 정리
- 기존 안내 메시지가 "GPU-backed deployment" 라고만 되어 있어 오해 소지가 있었음
- 이제는 "public API server에서 `STEP4_ENABLE_STRUCTURE_JOBS=true` + GPU host에서 worker 실행" 으로 더 명확히 표현

### 5) G5 준비용 운영 파일 추가
- `ops/ec2/env.api.with_gpu_worker.example`
- `ops/ec2/colabfold_batch_worker.example.sh`
- `ops/ec2/README_G5_STEP4_WORKER.md`
- `supabase/sql/2026-04-12_step4_structure_job.sql`

## 적용 대상
- CPU API 서버 (`t3.small`)
  - 코드 덮어쓰기
  - `.env.backend` 에 `STEP4_ENABLE_STRUCTURE_JOBS=true` 로 전환할 준비
- GPU worker 서버 (`g5.xlarge`)
  - 같은 `backend/` 코드 업로드
  - `.env.worker` 사용
  - `scripts/run_step4_jobs.py` 실행
