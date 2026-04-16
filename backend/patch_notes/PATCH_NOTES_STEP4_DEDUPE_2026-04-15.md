STEP4 protein-structure dedup patch (2026-04-15)

What changed:
- Added global lookup by `result_payload.user_protein_sha256` in `structure_job_repo.py`.
- `POST /api/states/{state_id}/step4/jobs` now reuses an existing identical-protein ColabFold job/result across *all* states before queueing a new GPU job.
- Baseline reuse is checked before the global STEP4_ENABLE_STRUCTURE_JOBS gate, so reuse still works even if the GPU worker is offline.
- `GET /api/states/{state_id}/step4` now surfaces a reusable global identical-protein job in `latest_structure_job` / `structure_jobs` when the current state has no usable local job.
- Added SQL indexes for provider/status and `result_payload->>'user_protein_sha256'`.

Files changed:
- app/db/repositories/structure_job_repo.py
- app/services/structure_job_service.py
- app/services/step4_state_service.py
- 2026-04-15_step4_dedupe_indexes.sql

Expected behavior after deploy:
- If a user edits a gene to a protein sequence that has already been predicted before, t3 reuses the existing STEP4 job/result instead of creating another GPU job.
- If g5 is OFF but a cached identical-protein prediction already exists, t3 can still return that existing structure result.
- If the current user protein matches the normal protein, baseline reuse still works as before.
