# STEP3 frontend-ready overlay patch (2026-03-13)

This overlay extends the existing STEP3 splicing endpoint so the frontend can consume:

- `frontend_summary`
- `canonical_sites`
- `novel_sites`
- `interpreted_events`
- `logic_thresholds`

without changing the existing `prob_ref` / `prob_alt` contract.

## What changed

### 1) New heuristic interpretation layer
Added `app/services/step3_interpreter.py`.

It turns raw STEP3 probabilities into two layers:

- **site level**
  - canonical donor / acceptor sites
  - novel donor / acceptor gain candidates
- **event level**
  - `PSEUDO_EXON`
  - `EXON_EXCLUSION`
  - `BOUNDARY_SHIFT`
  - `CANONICAL_STRENGTHENING`

### 2) STEP3 response model expanded
`app/schemas/splicing.py` now includes structured frontend-ready fields while preserving the original payload.

### 3) STEP3 service integration
`app/services/splicing_service.py` now calls the interpreter after inference and adds the interpretation block to the response.

### 4) Dev GUI improved
`dev_gui/app.py` now shows:

- primary frontend summary
- interpreted events
- canonical / novel site lists
- logic thresholds

## Heuristic logic in this patch

This patch intentionally follows a **delta-first** approach and does **not** treat raw absolute probability as the primary decision rule.

### General thresholds used
- general spliceogenicity threshold: `0.20`
- non-spliceogenic / weak zone lower guidance: `0.10`
- pseudoexon donor/acceptor pair threshold: `0.05`
- weak candidate site threshold: `0.02`
- pseudoexon size window: `25..500 bp`
- strong relative canonical drop: `alt / ref <= 0.5`

### Event rules
#### PSEUDO_EXON
- paired **novel acceptor + novel donor**
- both inside the **same intron**
- acceptor before donor
- size in `25..500 bp`
- motif sanity checked on the ALT sequence when possible

#### EXON_EXCLUSION
- one or both canonical sites for an exon show strong loss
- uses **delta loss** and **relative drop**
- if a same-exon boundary shift also exists, exclusion confidence is reduced

#### BOUNDARY_SHIFT
- novel site of the **same class** near a canonical boundary
- supports:
  - `EXON_EXTENSION_5P`
  - `EXON_EXTENSION_3P`
  - `EXON_SHORTENING_5P`
  - `EXON_SHORTENING_3P`

#### CANONICAL_STRENGTHENING
- useful for rescue / exon inclusion restoration style edits
- intended for cases like SMN2-style rescue exploration

## Important scope note
This patch is **frontend-ready**, not **clinically final**.

It is designed to:
- make STEP3 interpretable in the UI now
- keep probabilities available for plotting
- leave room for later upgrades:
  - transcript reconstruction
  - cDNA / CDS / protein generation
  - translation sanity
  - persistence into `baseline_result` / `user_state_result`

## Files included
- `app/schemas/splicing.py`
- `app/services/splicing_service.py`
- `app/services/step3_interpreter.py`
- `dev_gui/app.py`
