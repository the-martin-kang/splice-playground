# Backend restore bundle (app + dev_gui)

Unzip this into your backend project root. It will create:

- app/       (FastAPI backend)
- dev_gui/   (Streamlit dev GUI)

Then run backend:
```bash
uv run uvicorn app.main:app --reload --port 8000
```

And run GUI:
```bash
uvx --with matplotlib streamlit run dev_gui/app.py
```
