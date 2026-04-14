# Patch notes: STEP4 backend optimization overlay (2026-04-14)

## Purpose
Stabilize STEP4 GPU job handling after timeouts and oversized payloads during ColabFold smoke tests.

## Key changes
- compacted `structure_job.result_payload`
- summary/detail repository fetch split for `structure_job`
- reduced ColabFold artifact uploads by default
- added retry/backoff for repo/storage operations
- lowered idle queue pressure via 15s polling default
- added maintenance script to compact existing historical rows
- added SQL indexes for queue/state access patterns
- added `.gitignore` hygiene for deployable repo

## Recommended rollout order
1. Apply overlay to local backend
2. Apply SQL: `supabase/sql/2026-04-14_step4_perf_indexes.sql`
3. Deploy updated code to t3 API and g5 worker
4. Set env:
   - `STEP4_ARTIFACT_POLICY=minimal`
   - `STEP4_JOB_POLL_SECONDS=15`
   - `SUPABASE_RETRY_ATTEMPTS=3`
   - `SUPABASE_RETRY_BACKOFF_SECONDS=0.75`
5. Restart services
6. Run one-time compaction for old succeeded jobs if needed

## Historical rows already affected by oversized payloads
Use:
```bash
uv run scripts/compact_structure_jobs.py --provider colabfold --status succeeded --limit 50
```
