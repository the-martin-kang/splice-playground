# STEP3 backend patch (SpliceAI-10k, 7-region inference)

## What this adds
- `/api/splicing/predict` (POST)
  - Builds **target span = focus region ±3** (7 regions) around representative SNV.
  - Builds **input span = target span ± flank** (default flank=5000) using **real upstream/downstream region sequences**.
    - Only pads with 'N' if sequence is missing (gene boundary / uncovered positions).
  - Runs model (SpliceAI ResBlock) and returns probability tracks over the **target span only**.

## Files
- `app/ai_models/spliceai10k_resblock.py`
- `app/schemas/splicing.py`
- `app/services/splicing_service.py`
- `app/api/routes/splicing.py`

## Required wiring
1) Include router in your API router (e.g. `app/api/router.py`)
```py
from app.api.routes import splicing
api_router.include_router(splicing.router)
```

2) Environment variables (recommended)
- `SPLICEAI_MODEL_PATH` (default: `app/ai_models/spliceai_window=10000.pt`)
- `SPLICEAI_MODEL_VERSION` (default: `spliceai10k`)
- `SPLICEAI_DEVICE` (default: `cpu`)  # local mac can try `mps`

3) Docker image must include the model weight
If your `.dockerignore` ignores `*.pt`, add an exception:
```
!app/ai_models/*.pt
```

## Quick test
```bash
curl -sS -X POST "http://localhost:8000/api/splicing/predict" \
  -H "Content-Type: application/json" \
  -d '{"disease_id":"CFTR_gene0_109442_A>G","edits":[]}' \
| python3 -c "import json,sys; d=json.load(sys.stdin); print(d['gene_id'], d['target_len'], d['center_index_0'])"
```
