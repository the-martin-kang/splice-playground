# STEP4 G5 worker deployment

이 문서는 `g5.xlarge` EC2에 STEP4 ColabFold worker를 올릴 때 필요한 최소 단계만 정리합니다.

## 아키텍처
- public API 서버: `t3.small` (FastAPI + Caddy)
- GPU worker: `g5.xlarge` (ColabFold + `scripts/run_step4_jobs.py`)
- 두 서버는 서로 직접 통신하지 않고 Supabase `structure_job` 큐와 Storage를 통해 연결됩니다.

## 사전 조건
1. Supabase SQL editor에서 `supabase/sql/2026-04-12_step4_structure_job.sql` 실행
2. CPU API 서버 `.env.backend` 에서 `STEP4_ENABLE_STRUCTURE_JOBS=true` 로 변경
3. public API 서버 재시작

## GPU EC2 최소 사양
- AMI: Deep Learning AMI with Conda (Ubuntu)
- type: `g5.xlarge`
- disk: 150~200GB gp3
- inbound: SSH 22 only (your IP)
- outbound: all

## worker env 핵심값
`.env.worker` 예시:

```dotenv
APP_NAME=splice-playground-step4-worker
APP_VERSION=0.1.0
API_PREFIX=/api
CORS_ORIGINS=

SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_ANON_KEY=YOUR_ANON_KEY

STEP4_STRUCTURE_BUCKET=structure-assets
SIGNED_URL_EXPIRES_IN=3600

COLABFOLD_BATCH_CMD=/usr/local/bin/colabfold_batch_worker
COLABFOLD_EXTRA_ARGS=
STEP4_JOB_WORKDIR=/data/step4_jobs
STEP4_JOB_TIMEOUT_SECONDS=21600
STEP4_ALIGNMENT_BIN=
```

## 설치 순서
1. `backend/` 코드를 GPU EC2에 업로드
2. `uv sync`
3. ColabFold conda env 생성
4. `/usr/local/bin/colabfold_batch_worker` wrapper 설치
5. `uv run scripts/run_step4_jobs.py --once` 로 빈 큐 확인
6. `systemd` 로 상시 실행

## ColabFold wrapper
`ops/ec2/colabfold_batch_worker.example.sh` 참고

## smoke test
### API 서버에서 STEP4 job 생성
```bash
curl -X POST \
  -H 'content-type: application/json' \
  https://api.splice-playground-api.com/api/states/<STATE_ID>/step4/jobs \
  -d '{"provider":"colabfold","force":false,"reuse_if_identical":true}'
```

### worker 수동 실행
```bash
uv run scripts/run_step4_jobs.py --once
```

### job 조회
```bash
curl https://api.splice-playground-api.com/api/step4-jobs/<JOB_ID>
```

## 주의
- 현재 worker는 `provider=colabfold` 만 처리합니다.
- baseline과 동일 protein이면 API 서버가 `baseline_reuse` 성공 job을 즉시 생성하므로 GPU worker가 할 일이 없습니다.
- 실제 ColabFold 구조 job은 `same_as_normal=false` 인 state에서 확인해야 합니다.
