# PATCH NOTES — EC2 split deploy helpers + STEP4 dev GUI

## Added deployment helper files

New folder: `ops/ec2/`

Included:
- `README_EC2_SPLIT_DEPLOY.md`
- `env.backend.example`
- `env.worker.example`
- `splice-backend-api.service`
- `splice-step4-worker.service`
- `Caddyfile.backend.example`

Purpose:
- run the FastAPI backend on a small CPU EC2
- run the ColabFold STEP4 worker on a separate GPU EC2
- keep the two servers connected only through Supabase + Storage
- avoid direct server-to-server RPC

## Added CLI smoke test

New file:
- `scripts/step4_smoke_test.py`

Purpose:
- create or reuse a STEP4 job from the command line
- poll until terminal state
- quickly verify backend + worker + storage integration without the frontend

## Updated developer GUI

Updated files:
- `dev_gui/app.py`
- `dev_gui/README.md`

New STEP4 features:
- fetch `/api/states/{state_id}/step4`
- create `/api/states/{state_id}/step4/jobs`
- refresh `/api/step4-jobs/{job_id}`
- inspect normal track vs user track side by side
- render normal structure assets
- render user structure assets
- inspect translation sanity, protein comparison, ColabFold confidence, and structure-comparison payloads

## Validation performed

- `python -m compileall app scripts dev_gui ops/ec2` passed
