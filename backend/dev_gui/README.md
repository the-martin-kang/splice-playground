# splice-playground dev GUI

This folder is now a **separate uv project**.

Why:
- the root backend project depends on `pandas>=3.0.0`
- modern Streamlit releases that support Altair 6 still require `pandas<3`
- installing Streamlit into the root backend environment makes dependency resolution impossible

## Run the backend env

```bash
cd backend
uv sync
```

## Run the dev GUI env

```bash
cd backend/dev_gui
uv sync
uv run streamlit run app.py
```

## Important

Do **not** run `uv add streamlit` from the backend root anymore.
Use the isolated `dev_gui/` project instead.
