# PATCH NOTES — dev_gui Streamlit compatibility fix (2026-03-29)

## Root cause
The repo pinned `streamlit==1.19.0` in `uv.lock`, but `uv add streamlit` also resolved `altair==6`.
That pair is incompatible because Streamlit 1.19 imports `altair.vegalite.v4`, which does not exist in Altair 6.

## Fix
- `pyproject.toml` now explicitly requires:
  - `streamlit>=1.52.0,<2`
  - `altair>=6,<7`
- `dev_gui/README.md` now explains the failure mode and the exact refresh commands.

## Apply
From the backend root after overlaying these files:

```bash
uv sync --upgrade-package streamlit --upgrade-package altair
```

If the environment is badly stale:

```bash
rm -rf .venv
uv sync
```
