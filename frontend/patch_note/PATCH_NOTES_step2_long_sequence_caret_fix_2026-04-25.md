# STEP2 long-sequence caret alignment fix — 2026-04-25

## Problem

In long PMM2 intron sequences, clicking a visible base and pressing Backspace/Delete could replace a nucleotide several positions away with `N`. Short exon editing still worked.

Root cause: the editor rendered two different text layers:

- visible diff-highlight backdrop: inline `<span>` bases with CSS wrapping (`break-all`, `whitespace-pre-wrap`)
- invisible interactive `<textarea>`: browser-native textarea wrapping and hit-testing

For very long unbroken DNA strings, the two layers can wrap at slightly different positions in production browsers. Once wrapping diverges, the caret from the transparent textarea no longer points to the same visible nucleotide in the backdrop. The offset grows by line and appears as a 5–20 bp deletion mismatch.

## Strategy

Do not roll back the redesigned UI. Keep the diff-highlight overlay approach, but make the visual layer and the interactive textarea use the exact same displayed text.

## Changed files

- `app/components/step2/useRegionSequenceEditor.ts`
- `app/components/step2/SequenceEditor.tsx`
- `app/components/step2/Step2DnaEditor.tsx`

## Key changes

### 1. Fixed visual wrapping by inserting deterministic line breaks

Raw DNA sequence is still stored without newlines, but the editor display is formatted into fixed 64 bp lines.

This removes browser-dependent soft-wrapping mismatch between the backdrop and textarea.

### 2. Added raw/display caret mapping

Textarea `selectionStart` now belongs to the formatted display string, so the hook maps:

- display caret index → raw DNA index before editing
- raw DNA index → display caret index after editing

The backend/localStorage payload remains the original raw sequence without inserted newlines.

### 3. Preserved fixed-length DNA editing semantics

- Backspace/Delete still replace bases with `N`
- valid A/C/G/T/N input still overwrites in place
- invalid keys still do not insert or move the caret
- paste still normalizes and overwrites without changing sequence length
- selection delete/cut still converts the selected raw base range to `N`

### 4. Kept previous Vercel event-race protections

The hook now keeps the native `keydown` / `beforeinput` / `change` guard path so valid input is not double-applied and invalid input does not advance the caret.

## Not changed

- STEP2 UI design and image
- STEP1, STEP3, STEP4
- Spline background
- Mol* viewer
- backend/API contract
- Supabase logic

## Verification performed

- TypeScript transpile syntax check for all `app/**/*.ts` and `app/**/*.tsx`: passed
- Diff confirmed only 3 STEP2 files changed

## Manual test checklist

1. PMM2 long intron: click a visible base and press Delete → that exact visible base becomes `N`
2. PMM2 long intron: click after a visible base and press Backspace → immediately previous visible base becomes `N`
3. Repeat near line starts/line ends
4. Type `A` on an `N` → exactly one `A` appears
5. Type invalid `H` → no insertion and caret does not move
6. Select across multiple lines and Delete → selected bases become `N`, sequence length unchanged
7. Paste A/C/G/T sequence across a line break → overwrite only, length unchanged
8. Short exon editing still behaves the same
