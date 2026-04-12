# STEP4 stateful 2-track backend

## 목표
STEP4는 항상 두 개의 track을 분리해서 반환합니다.

1. **normal track**
   - canonical baseline protein
   - Supabase에 저장된 baseline structure assets
   - read-only

2. **user track**
   - STEP2/STEP3를 거친 current transcript
   - current cDNA / CDS / protein
   - translation sanity
   - normal 대비 protein 비교
   - structure prediction job 상태

## API

### baseline only
- `GET /api/diseases/{disease_id}/step4-baseline`
- `GET /api/states/{state_id}/step4-baseline`

### stateful STEP4
- `GET /api/states/{state_id}/step4`
- `POST /api/states/{state_id}/step4/jobs`
- `GET /api/step4-jobs/{job_id}`

## worker
App Runner/FastAPI는 job 생성/조회만 담당하고, 실제 ColabFold 실행은 별도 worker가 담당합니다.

예:
```bash
uv run scripts/run_step4_jobs.py --once
```

지속 polling:
```bash
uv run scripts/run_step4_jobs.py
```

특정 job만:
```bash
uv run scripts/run_step4_jobs.py --job-id <JOB_ID>
```

## 권장 운영 구조
- FastAPI / App Runner: step4 job enqueue + polling API
- GPU worker(ECS or local GPU host): `scripts/run_step4_jobs.py`
- Storage: `structure-assets/`

## 주요 제한
- 현재는 STEP3 `primary_event` 기반 transcript reconstruction만 구현됨
- `COMPLEX` event는 canonical transcript fallback
- 구조 예측 provider는 현재 `colabfold` 경로만 실제 코드로 연결됨
- AlphaFold Server/API 자동 연동은 추후 provider로 확장
