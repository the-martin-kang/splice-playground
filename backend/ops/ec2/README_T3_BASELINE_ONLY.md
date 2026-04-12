# STEP4 baseline-only deployment on a single `t3.small`

This mode is for the period before the GPU worker is ready.

What works now:
- STEP1 / STEP2 / STEP3 API
- `GET /api/states/{state_id}/step4`
- `GET /api/diseases/{disease_id}/step4-baseline`
- `GET /api/states/{state_id}/step4-baseline`
- normal baseline protein sequence + structure assets from Supabase Storage
- Mol* can render the returned signed `.cif` / `.pdb` normal structure URL

What is intentionally disabled now:
- user-structure prediction jobs (`POST /api/states/{state_id}/step4/jobs`)
- ColabFold worker polling

The CPU server must set:

```dotenv
STEP4_ENABLE_STRUCTURE_JOBS=false
SPLICEAI_DEVICE=cpu
```

Recommended frontend flow:
1. create/fetch `state_id`
2. run STEP3 if needed
3. call `GET /api/states/{state_id}/step4?include_sequences=true`
4. read `normal_track.molstar_default.url` and `normal_track.molstar_default.format`
5. render the normal structure in Mol*
6. read `user_track.structure_prediction_enabled`
7. if `false`, show a "GPU worker not connected yet" badge and hide the predict button

Useful smoke test:

```bash
uv run scripts/step4_smoke_test.py \
  --backend-url https://api.example.com \
  --state-id <STATE_ID>
```

In baseline-only mode the script treats `created=false` from the job endpoint as a successful check.
