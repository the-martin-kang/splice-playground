# splice-playground dev GUI (STEP1~STEP3)

This Streamlit UI is for development/testing only.

## Run (minimal deps via uvx)
From backend root:

```bash
uvx --with matplotlib streamlit run dev_gui/app.py
```

If you prefer using project uv env:
```bash
uv add streamlit matplotlib
uv run streamlit run dev_gui/app.py
```

## What it does
- STEP1: GET /api/diseases
- STEP2: GET /api/diseases/{disease_id}
- STEP2-2: POST /api/diseases/{disease_id}/states
- STEP3: POST /api/states/{state_id}/splicing  (A 방식)

The backend must be running and have API_PREFIX=/api (default).
