# Mission6 Validation Package (splice-playground)

This folder contains a small Python package that reproduces the **Mission6** notebook logic:

- 4000bp input window with the variant at index 2000 (0-based)
- gene-outside masking with `N` (one-hot zeros)
- **negative strand**: the Mission6 off-by-one fix (`start += 1; end += 1` before reverse-complement)
- `ref/alt` bases are provided in **positive strand** coordinates (Mission6 convention)
  - for negative strand, the inserted `alt` is reverse-complemented

## Quick start

```bash
# from backend/ or repo root, adjust PYTHONPATH to include this folder
export PYTHONPATH=$PWD:$PYTHONPATH

python -m validation.mission6.validate_backend \
  --selected path/to/selected_gene.tsv \
  --annotation path/to/Mission6_refannotation.tsv \
  --fasta path/to/Mission6_refgenome.fa \
  --model path/to/mission5.pt \
  --backend-url https://YOUR_AWS_APP_RUNNER_URL \
  --out validation_report.json
```

The script expects your backend to expose:
- `GET /api/diseases` (returns list with `disease_id` and `gene_id`)
- `GET /api/diseases/{disease_id}/window_4000` (returns `ref_seq_4000`, `alt_seq_4000`)

If you haven't added `/window_4000` yet, add it first (recommended) because it removes the need to
"merge regions then slice to 4000" on the client side.
