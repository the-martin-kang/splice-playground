# ai_models

- `spliceai_window=10000.pt`: default model checkpoint path used by the backend.
  - Override with env: `SPLICEAI_MODEL_PATH=/abs/path/to/your_model.pt`

- `spliceai_resblock.py`: lightweight SpliceAI-like ResBlock model definition (PyTorch).
- `spliceai_inference.py`: one-hot + center-crop inference helpers.
