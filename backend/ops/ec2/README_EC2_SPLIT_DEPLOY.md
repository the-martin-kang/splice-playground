# EC2 split deployment guide (CPU backend + GPU STEP4 worker)

## Recommended monorepo shape

Recommended root folders:

- `backend/` — FastAPI app, shared domain logic, STEP3/STEP4 APIs, baseline ingestion, worker script
- `frontend/` — Vercel app
- `ops/` — deployment notes, systemd units, reverse proxy config, env examples

If you really want a third application-like folder, prefer `step4_worker/` over `colabfold_backend/`.
`step4_worker` should stay thin: service wrappers and deployment files only.
Do **not** fork the Python application code into a second backend copy.
The actual worker entrypoint remains:

```bash
backend/scripts/run_step4_jobs.py
```

## Two EC2 servers

### 1) CPU EC2 (always on)
Purpose:
- public HTTPS backend API for Vercel frontend
- SpliceAI / STEP1~STEP4 API
- no GPU

Recommended instance type:
- `t3.small` first
- raise to `t3.medium` only if CPU or RAM becomes tight

### 2) GPU EC2 (turn on only when needed)
Purpose:
- ColabFold worker for STEP4 user-structure jobs
- not public
- no direct frontend traffic

Recommended instance type:
- `g5.xlarge` on-demand

## Security groups

### CPU backend security group
Inbound:
- TCP 22 from **your public IP only**
- TCP 80 from `0.0.0.0/0`
- TCP 443 from `0.0.0.0/0`

Outbound:
- allow all

### GPU worker security group
Inbound:
- TCP 22 from **your public IP only**

Outbound:
- allow all

No inbound rule from the CPU backend is required.
The CPU backend and GPU worker are logically connected through:
- Supabase Postgres / API
- Supabase Storage

The CPU server writes `structure_job` rows.
The GPU worker polls queued jobs, runs ColabFold, uploads artifacts, and updates the same rows.

## Files in this folder

- `env.backend.example`
- `env.worker.example`
- `splice-backend-api.service`
- `splice-step4-worker.service`
- `Caddyfile.backend.example`

## Quick deployment order

1. Stop or delete the old App Runner service.
2. Launch CPU EC2.
3. Attach Elastic IP to CPU EC2.
4. Point your API DNS record to that Elastic IP.
5. Clone repo on CPU EC2 and configure backend.
6. Install Caddy and run FastAPI behind it.
7. Launch GPU EC2 with a DLAMI.
8. Clone the same repo on GPU EC2.
9. Install ColabFold in a dedicated conda environment.
10. Run `scripts/run_step4_jobs.py` as a systemd service.
11. Test with `dev_gui` or `scripts/step4_smoke_test.py`.

## CPU EC2 app layout example

```text
/home/ubuntu/splice-playground/
└── backend/
    ├── .env.backend
    ├── app/
    ├── scripts/
    ├── ops/
    └── uv.lock
```

## GPU EC2 app layout example

```text
/home/ubuntu/splice-playground/
└── backend/
    ├── .env.worker
    ├── app/
    ├── scripts/
    ├── ops/
    └── uv.lock
```

## CPU backend startup checklist

```bash
uv sync
cp ops/ec2/env.backend.example .env.backend
# edit values
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If that works, switch to the systemd service in `splice-backend-api.service` and put Caddy in front.

## GPU worker startup checklist

```bash
uv sync
cp ops/ec2/env.worker.example .env.worker
# edit values
uv run scripts/run_step4_jobs.py --once
```

Before running the worker continuously, verify that:
- `nvidia-smi` works
- `colabfold_batch` works in the dedicated conda environment
- `COLABFOLD_BATCH_CMD` points to the wrapper script that enters that environment

## Why this split is simpler than direct server-to-server calls

This design avoids custom RPC between the two EC2 instances.
That keeps maintenance simple:

- backend server only needs HTTPS + Supabase credentials
- worker only needs outbound internet + Supabase credentials + GPU
- worker can be stopped without breaking STEP1~STEP3
- normal STEP4 baseline stays available even while the worker is off

## Testing sequence

1. `curl https://api.your-domain/healthz`
2. open `dev_gui`, fetch disease, create state, run STEP3
3. fetch STEP4 state
4. create STEP4 structure job
5. check GPU worker logs with `journalctl -u splice-step4-worker -f`
6. refresh STEP4 state / job
7. render normal structure and user structure in `dev_gui`
