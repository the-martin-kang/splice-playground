# PATCH NOTES — dev_gui isolated project + root backend restore (2026-03-29)

## Root cause
The previous fix upgraded Streamlit in the **root backend project**.
That made `uv sync` impossible because:
- root backend depends on `pandas>=3.0.0`
- Streamlit versions new enough to support Altair 6 still require `pandas<3`

## Fix
- Restored the root `pyproject.toml` so the backend runtime no longer depends on Streamlit/Altair.
- Added a separate `dev_gui/pyproject.toml` for the local Streamlit test app.
- Added `dev_gui/.gitignore` so its virtualenv stays isolated.

## New commands
Backend runtime env:
```bash
cd backend
rm -rf .venv
uv sync
```

Dev GUI env:
```bash
cd backend/dev_gui
uv sync
uv run streamlit run app.py
```
