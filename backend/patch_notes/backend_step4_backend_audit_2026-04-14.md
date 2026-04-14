# STEP4 backend audit and optimization report (2026-04-14)

## What was going wrong

1. `structure_job.result_payload` became too large.
   - queued jobs stored full `user_protein_seq`, full transcript blocks, full baseline asset lists.
   - succeeded jobs kept that input payload *plus* every uploaded asset reference and worker metadata.
   - `/api/step4-jobs/{job_id}` and `/api/states/{state_id}/step4` both loaded `result_payload`, so a single large job row could make readback slow or timeout.

2. The worker uploaded too many artifacts per job.
   - one full ColabFold run uploaded `query.fasta`, logs, all per-rank score JSONs, all per-rank PDBs, PAE, A3M/MSA artifacts, config, done marker, etc.
   - this created a burst of storage requests and extra load on Supabase Storage.

3. The worker polled too frequently.
   - default queue polling interval was 5 seconds.
   - idle polling volume was higher than necessary for an async queue.

4. Some read paths fetched large sequence columns unnecessarily.
   - `list_protein_references_by_gene()` always selected canonical mRNA / CDS / protein strings even when the caller only needed metadata.

5. API and worker reads lacked retry logic.
   - transient Supabase / Storage timeouts (`522`, `544`) could immediately bubble up instead of retrying.

6. Deployment hygiene was weak.
   - repo/zip contents included `.venv`, `.idea`, `.DS_Store`, which wastes bandwidth and risks stale local-state leakage.

## What was improved

### A. Smaller `structure_job` payloads
- queued ColabFold jobs now store only the fields the worker actually needs.
- succeeded jobs now store a compact summary payload:
  - `user_protein_sha256`
  - `user_protein_length`
  - compact `comparison_to_normal`
  - compact `translation_sanity`
  - compact `predicted_transcript` summary
  - `assets`
  - `confidence`
  - `worker`
  - optional `structure_comparison`
- large input sequence strings are no longer persisted in completed job rows.

### B. Lighter job list / job state fetches
- repository methods now support summary vs detail fetches.
- state-level STEP4 hydration fetches only a small job history and at most one detailed latest job.
- `/api/step4-jobs/{job_id}` supports `include_payload=false` for summary-only fetches.

### C. Fewer uploaded artifacts by default
- new default policy: `STEP4_ARTIFACT_POLICY=minimal`
- uploads only the files needed for reproducibility / viewing by default:
  - input FASTA
  - stdout / stderr logs
  - best-ranked structure file
  - ranking / config / PAE level metadata
- no longer uploads every rank structure and every heavy auxiliary artifact unless explicitly switched to `full`.

### D. Retry / backoff on transient Supabase / Storage errors
- common repo and storage calls now retry with exponential backoff on timeout-like failures.

### E. Lower idle queue traffic
- default worker poll interval increased from 5s to 15s.

### F. Repo hygiene
- added `.gitignore` so local env/editor junk is no longer treated like deployable code.

## Files changed
- `.gitignore`
- `app/core/config.py`
- `app/db/repositories/_helpers.py`
- `app/db/repositories/structure_job_repo.py`
- `app/db/repositories/step4_baseline_repo.py`
- `app/services/storage_service.py`
- `app/services/step4_baseline_service.py`
- `app/services/step4_state_service.py`
- `app/services/structure_job_service.py`
- `app/api/routes/step4.py`
- `scripts/run_step4_jobs.py`
- `scripts/compact_structure_jobs.py`
- `ops/ec2/env.backend.example`
- `ops/ec2/env.api.with_gpu_worker.example`
- `ops/ec2/env.worker.example`
- `ops/ec2/colabfold_batch_worker.example.sh`
- `ops/ec2/splice-step4-worker.service`
- `supabase/sql/2026-04-14_step4_perf_indexes.sql`

## One-time cleanup recommended
For existing oversized job rows already written to Supabase:

```bash
uv run scripts/compact_structure_jobs.py --provider colabfold --status succeeded --limit 50
```

This rewrites large historical `result_payload` JSON blobs into compact summaries so future GETs are lighter.

## New env knobs
- `SUPABASE_RETRY_ATTEMPTS=3`
- `SUPABASE_RETRY_BACKOFF_SECONDS=0.75`
- `STEP4_JOB_POLL_SECONDS=15`
- `STEP4_MAX_STATE_JOB_SUMMARY=3`
- `STEP4_ARTIFACT_POLICY=minimal`

## New SQL
Apply:
- `supabase/sql/2026-04-14_step4_perf_indexes.sql`

This adds indexes that help common STEP4 queue/state access patterns.
