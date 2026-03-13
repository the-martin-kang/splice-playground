# Backend overlay patch (2026-03-13)

This zip is meant to be extracted **from the backend root** so the included files overwrite the existing ones.

## Main changes

### 1) Step3 now respects `parent_state_id` lineage
- `app/services/state_lineage.py` added.
- STEP3 predictions now apply parent-chain edits before the current state's edits.
- This aligns inference with the sequence that STEP2 edit validation already uses.

### 2) `max_supported_step` gate fixed
- STEP3 now properly returns **403** when `disease.max_supported_step < 3`.
- The old broad `except` no longer swallows this check.

### 3) Disease → gene resolution unified
- `app/services/gene_context.py` added.
- `disease.gene_id` is still the preferred source.
- If missing, services now consistently fall back to `disease_gene` bridge resolution when exactly one gene is linked.

### 4) STEP3 response now includes more useful metadata
- `state_lineage`
- `effective_edits`
- `warnings`
- `delta_summary`
- gene-direction representative SNV alleles
- whether the representative disease SNV was actually applied

### 5) Dev GUI improved for debugging
- Added `include_parent_chain` toggle.
- Shows delta summary / warnings / effective lineage and edits.

## Files included
- app/api/routes/splicing.py
- app/schemas/splicing.py
- app/services/disease_service.py
- app/services/gene_context.py
- app/services/splicing_service.py
- app/services/state_lineage.py
- app/services/state_service.py
- dev_gui/app.py
- PATCH_NOTES_backend_overlay_2026-03-13.md

## Quick sanity check after applying
```bash
python -m compileall app dev_gui
```
