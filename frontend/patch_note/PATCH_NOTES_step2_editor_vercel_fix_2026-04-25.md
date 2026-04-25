# STEP2 DNA Editor Vercel input regression fix — 2026-04-25

## Scope

This patch only changes STEP2 DNA editor logic.

Changed file:

```text
app/components/step2/useRegionSequenceEditor.ts
```

Unchanged:

```text
STEP1 UI
STEP2 layout / images / styling
STEP3
STEP4
Mol* viewers
Spline background
Backend/API contracts
```

## Problem observed in Vercel production

In local `npm run dev`, STEP2 editing looked correct. In Vercel production:

1. Backspace/Delete correctly changed a base to `N`.
2. Typing `A` into that `N` position could produce two `A`s.
3. Typing an invalid key such as `H` did not insert `H`, but the caret advanced by one as if ArrowRight had been pressed.

## Root cause

The DNA editor is a controlled `<textarea>`, but it also manually handles fixed-length edits through:

- `keydown`
- `beforeinput`
- `change` fallback

In production browsers/React builds, `beforeinput` or native `change` can still arrive around a manually handled `keydown`. That means a single physical key press can be processed twice:

```text
keydown custom overwrite
+ beforeinput/change fallback overwrite
= duplicated valid base
```

For invalid keys, the browser-native value could briefly contain the invalid character, then the fallback sanitizer removed it but preserved the browser-advanced caret position:

```text
H inserted natively for a moment
sanitize removes H
caret remains +1
```

## Fix

### 1. Add live sequence ref

`currentSequenceRef` is updated synchronously inside `commitSequence`. Event handlers now read from this live ref instead of relying only on React state closure timing.

### 2. Add guarded native event handling

After a custom `keydown` edit, the hook arms a short guard containing the intended sequence and caret.

If `beforeinput` fires for the same physical key press, it is suppressed.

If `change` still fires, the guarded intended sequence/caret is restored instead of interpreting the browser-mutated textarea value again.

### 3. Make invalid-key caret stable

Invalid keys now explicitly re-commit the same sequence with the original caret position. If the browser still emits a native fallback event, the guard restores that same caret.

### 4. Improve native fallback reconciliation

The fallback `onChange` path no longer sanitizes the entire textarea by truncating from the front. It now compares the previous controlled sequence with the native textarea value and reconstructs one fixed-length operation:

- native insert → overwrite only the affected range
- native invalid insert → keep sequence and caret at the original position
- native delete → replace removed range with `N`

## Expected behavior after patch

- Backspace/Delete keeps sequence length and writes `N`.
- Typing `A/C/G/T/N` overwrites exactly one position.
- Typing invalid English keys such as `H` inserts nothing and does not move the caret.
- Selection delete/cut still becomes `N...N` rather than shortening the sequence.
- Paste remains fixed-length overwrite.

## Verification performed here

- TypeScript transpile syntax check passed for all 51 `app/**/*.ts(x)` files in the uploaded app bundle.
- Diff reviewed to confirm only STEP2 editor hook changed.
