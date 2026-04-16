# Splice Playground audit + patch notes (2026-04-16)

## Scope
Read and cross-checked:
- `splice_playground_master_handoff_2026-04-16.md`
- current `backend.zip`
- current `frontend.zip`

Rule used during this pass:
- handoff = product/biology/ops intent
- current zip code = actual implementation truth when handoff and code diverge

## Current state summary

### Backend
- FastAPI routing is organized around STEP1/2 (`diseases`, `states`), STEP3 (`splicing`), and STEP4 (`step4`).
- `state_service.py` correctly replays current sequence from reference + representative SNV + parent chain + current edit, and already respects `seed_mode`.
- `splicing_service.py` + `step3_interpreter.py` already contain the stronger biology logic:
  - delta-centric site interpretation
  - pseudo-exon detection
  - exon exclusion
  - boundary shift
  - canonical strengthening / rescue
- `step4_state_service.py` already provides:
  - baseline protein/structure
  - user transcript/protein reconstruction
  - baseline reuse when user protein == normal
  - global identical-protein reuse
  - g5-off fallback messaging
- `structure_job_service.py` and `structure_job_repo.py` already separate queue summary vs detailed payload and support reuse / dedupe.

### Frontend
- STEP2 editor is now textarea + aligned highlight backdrop, with overwrite semantics and delete/backspace -> `N`.
- STEP4 already has Normal / User / Overlay tabs, Mol* single-view and overlay-view paths, job submission, polling, and comparison cards.
- TypeScript checked cleanly.

### Runtime / deployment understanding
- Frontend assumes Next.js on Vercel.
- Public API assumes FastAPI on t3.
- User structure prediction assumes GPU worker on g5 polling Supabase jobs.
- Baseline STEP4 is expected to work even when g5 is off.
- Supabase is both DB and storage backbone.

## Problems found (severity order)

### Critical
1. **STEP2 seed_mode regression in frontend**
   - `DNAManipulator.tsx` always initialized the editable/current sequence from the representative SNV-applied sequence.
   - This violated `seed_mode=reference_is_current` diseases.

2. **STEP3 pseudo-exon visualization regression**
   - `MatureMRNA.tsx` rebuilt abnormal mRNA by striking through every `affected_exon_number`.
   - For `PSEUDO_EXON`, this incorrectly made the flanking canonical exons look excluded instead of inserting a pseudo-exon block between them.

3. **STEP4 success hydration / polling contract mismatch**
   - Frontend polled `/api/step4-jobs/{job_id}?include_payload=false`.
   - Backend summary rows intentionally omit `result_payload`, so terminal job refreshes did not contain `molstar_default`.
   - Result: job could finish successfully but the user structure/overlay would not auto-hydrate into the viewer.

### High
4. **API base URL regression**
   - `DiseaseSelector.tsx`, `DNAManipulator.tsx`, `MatureMRNA.tsx` had reverted to `http://localhost:8000`.
   - `Step4Protein.tsx` already used the production fallback.
   - This creates local-vs-Vercel contract drift.

5. **STEP4 view-mode regression**
   - Current code did not reliably auto-shift to the user/overlay view when the user structure became available, despite prior patch intent.

6. **STEP4 transcript block coloring semantics drift**
   - Transcript block coloring used `step3AffectedExons + excludedExons`.
   - In pseudo-exon cases, this risked painting flanking canonical exons as if they were excluded.

### Medium
7. **Signed URL remount sensitivity**
   - `mergeMolstarTarget()` preserved targets only by `structure_asset_id`.
   - Job-derived Mol* targets can lack `structure_asset_id`, so signed URL refreshes risked unnecessary remounts.

8. **Status spelling mismatch**
   - Frontend only recognized `cancelled`; backend uses `canceled`.

9. **Background regression**
   - Layout had reverted to live Spline iframe instead of the local static background asset, reintroducing runtime dependency / branding risk.

## Minimal fix strategy
- Keep backend source untouched unless a backend bug is the real root cause.
- Fix the frontend to match the existing backend/API contract.
- Restore prior intended behavior without broad refactors or UI redesign.

## Source changes applied

### Frontend
1. **Unified API base URL**
   - `app/components/DiseaseSelector.tsx`
   - `app/components/DNAManipulator.tsx`
   - `app/components/MatureMRNA.tsx`
   - switched to shared `app/lib/api.ts`

2. **STEP2 seed_mode fix**
   - `app/components/DNAManipulator.tsx`
   - current editable sequence now initializes from:
     - representative-SNV-applied sequence when `seed_mode != reference_is_current`
     - reference sequence when `seed_mode == reference_is_current`
   - edit detection (`edited` badge / diff summary) now compares against the real current-state baseline, not always SNV-seeded sequence

3. **STEP3 pseudo-exon / boundary-shift rendering fix**
   - `app/components/MatureMRNA.tsx`
   - introduced primary-event-aware rendering:
     - `PSEUDO_EXON` -> inserts amber `PseudoExon` block between flanking exons
     - `EXON_EXCLUSION` -> keeps dashed red strike-through styling
     - `BOUNDARY_SHIFT` -> marks the affected exon as shifted without excluding it
   - state creation now diffs the edited sequence against the true current-state seed sequence, preserving `seed_mode`

4. **STEP4 polling hydration + auto view fix**
   - `app/components/Step4Protein.tsx`
   - polling still uses lightweight job summary, but now:
     - when a job becomes terminal, the page re-fetches `/api/states/{state_id}/step4`
     - this hydrates the latest detailed job payload and makes the user structure available without requiring manual refresh
   - once the user structure first appears:
     - switch to `overlay` when user structure differs from baseline
     - switch to `user` when the user structure is a same-as-normal reuse

5. **STEP4 target stability fix**
   - `app/components/Step4Protein.tsx`
   - `mergeMolstarTarget()` now preserves a prior target not only by `structure_asset_id` but also by normalized URL path, reducing remounts when only signed query parameters rotate

6. **STEP4 transcript block semantics fix**
   - `app/components/Step4Protein.tsx`
   - canonical block exclusion coloring now keys off `excluded_exon_numbers`
   - non-excluded but involved exons are shown as amber “involved” badges instead of being colored like exclusions

7. **Status normalization**
   - `app/components/Step4Protein.tsx`
   - frontend now treats both `canceled` and `cancelled` as terminal failure-like statuses

8. **Background fallback restore**
   - `app/layout.tsx`
   - replaced live Spline iframe with local `/images/background.png`

### Backend
- **No backend source changes were required in this pass.**
- Existing backend behavior already matched the intended contracts for:
  - `seed_mode`
  - STEP3 biological interpretation
  - STEP4 baseline fallback
  - identical-protein reuse / dedupe
  - t3/g5 split job architecture

## Files changed
- `frontend/app/components/DiseaseSelector.tsx`
- `frontend/app/components/DNAManipulator.tsx`
- `frontend/app/components/MatureMRNA.tsx`
- `frontend/app/components/Step4Protein.tsx`
- `frontend/app/layout.tsx`

## Tests / checks run
- Frontend TypeScript: `./node_modules/.bin/tsc --noEmit` ✅
- Backend syntax sanity: `python -m py_compile $(find app -name '*.py')` ✅
- Frontend production build: attempted, but `next build` tried to download missing SWC binary from npm in an offline environment, so full production build could not be completed here. This is an environment/toolchain limitation, not a TypeScript failure.

## Recommended manual verification
1. STEP2
   - one `apply_alt` disease
   - one `reference_is_current` disease
   - verify no-change -> STEP3 works
   - verify delete/backspace -> `N`
   - verify refill after `N`
   - verify diff highlight/caret/selection remain aligned

2. STEP3
   - pseudo-exon case: flanking exons should remain canonical, amber pseudo-exon inserted
   - exon exclusion case: skipped exon should be dashed red/struck through
   - boundary shift case: affected exon should remain present but visually marked as shifted

3. STEP4
   - g5 off: baseline still visible
   - g5 on: create user job, wait for success, confirm automatic hydration into user/overlay view
   - cached prediction reuse path
   - same-as-normal reuse path
   - signed URL refresh should not flicker/remount unnecessarily

4. Deployment
   - verify disease list / STEP2 / STEP3 use the production API fallback on Vercel when `NEXT_PUBLIC_API_BASE_URL` is absent
