# Frontend patch notes (2026-04-14)

## Fixed issues

### 1) STEP2 DNA editor / indel-like overwrite behavior
- Replaced the fragile `contentEditable` sequence editor with a controlled `textarea` + fixed-length overwrite editor.
- Backspace/Delete now deterministically replace the targeted base(s) with `N` instead of shifting text.
- Typing `A/C/G/T/N` or Korean keyboard mappings (`ㅁ/ㅊ/ㅎ/ㅅ/ㅜ`) overwrites bases in place.
- Paste also works in fixed-length overwrite mode.
- Added explicit quick actions:
  - `Restore disease SNV`
  - `Restore reference`

### 2) STEP3 edit serialization
- Step3 now diffs **edited sequence vs seeded SNV sequence** without discarding `N` edits.
- This fixes three important paths:
  - keep the seeded disease SNV unchanged (`edits=[]`)
  - revert the disease SNV back to the reference allele
  - replace one or more positions with `N`

### 3) STEP4 page scroll / layout
- Removed the page-level `overflow-hidden` behavior that made long STEP4 screens feel clipped.
- Enabled vertical scrolling for the whole page.
- Added an overflow container for the right-side STEP4 detail column on large screens.

### 4) API base URL consistency
- Added `app/lib/api.ts` and unified components around the same `NEXT_PUBLIC_API_BASE_URL` fallback.

## Patched files
- `app/components/DNAManipulator.tsx`
- `app/components/MatureMRNA.tsx`
- `app/components/Step4Protein.tsx`
- `app/components/DiseaseSelector.tsx`
- `app/lib/api.ts`
