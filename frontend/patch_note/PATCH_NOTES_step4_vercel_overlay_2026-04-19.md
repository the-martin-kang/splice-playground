# STEP4 Vercel Protein Overlay Fix — 2026-04-19

## Scope

This patch only targets the STEP4 Protein Overlay failure observed on Vercel production:

- Normal Structure: working
- User Structure: working
- Overlay Compare: failing in production with `Cannot read properties of undefined (reading 'create')`
- Structure similarity: incorrectly shown as `0%` when overlay comparison failed

No STEP2, STEP3, API base URL, Spline background, layout, disease flow, or backend contract files were changed.

## Root cause assessment

The single-structure views already use the stable static Mol* iframe path under `public/vendor/molstar/index.html`.
The overlay path, however, used a separate runtime path inside `app/components/MolstarViewer.tsx`:

- dynamic ESM imports from `molstar/lib/...`
- direct `createPluginUI(...)`
- direct React root rendering
- direct TM-align imports and state transforms inside the Next/Vercel bundle

That path is exactly the historically fragile area for Vercel production builds. Local `npm run dev` can succeed while Vercel production fails because the Mol* ESM/runtime bundle path is different from the already-working iframe viewer path.

## Changed files

- `app/components/MolstarViewer.tsx`
- `app/components/Step4Protein.tsx`
- `public/vendor/molstar/overlay.html`

## Main changes

### 1. Production overlay now uses a static Mol* iframe

For `NODE_ENV === 'production'`, overlay mode now renders:

```text
/vendor/molstar/overlay.html
```

This keeps the known-good single-structure iframe strategy and avoids executing the fragile Next-bundled Mol* ESM overlay path in Vercel.

Local development keeps the previous direct Mol* overlay path so the existing local TM-align behavior is not rolled back.

### 2. Added `public/vendor/molstar/overlay.html`

The new static overlay viewer:

- loads the same prebuilt `molstar.js` bundle as the working single-structure viewer
- loads normal and user structures from signed URLs
- extracts C-alpha traces from the selected/preferred chain when possible
- sequence-aligns C-alpha residues
- applies Kabsch superposition in the iframe
- renders normal/user cartoons with the existing green/red color convention
- computes RMSD, aligned length, and TM-like structural scores
- sends the computed comparison back to the React parent through `postMessage`

### 3. Fixed false `0%` display

`Step4Protein.tsx` no longer treats an `unavailable` comparison object as a valid zero score.

Before:

```ts
Math.max(undefined ?? 0, undefined ?? 0) // 0%
```

After:

- if no numeric structural score exists, the UI shows `-`
- when overlay computation succeeds, the UI shows the computed structural score

### 4. Copy adjusted only where needed

Text that specifically said “TM-align” for every overlay was softened only for the overlay method display, because production now uses a Vercel-safe sequence-aligned C-alpha superposition path.

## Validation performed here

- `MolstarViewer.tsx` TypeScript syntax check through `typescript.transpileModule`: OK
- `Step4Protein.tsx` TypeScript syntax check through `typescript.transpileModule`: OK
- `public/vendor/molstar/overlay.html` embedded script syntax checked with `node --check`: OK

A full `next build` was not completed in this sandbox. The project bundle contains platform-specific SWC artifacts from the uploaded environment, and this Linux sandbox does not have the matching Next SWC binary available offline.

## Manual Vercel test checklist

1. Deploy the patched frontend to Vercel.
2. Open a STEP4 state where both normal and user structures exist.
3. Confirm Normal Structure still renders.
4. Confirm User Structure still renders.
5. Click Overlay Compare.
6. Confirm no `Cannot read properties of undefined (reading 'create')` appears.
7. Confirm the overlay iframe renders both structures: normal green, user red.
8. Confirm Structure Similarity is not falsely `0%`; it should be `-` while unavailable/loading or a computed percentage after overlay finishes.
9. Confirm buttons remain visible and switchable between Normal/User/Overlay.
10. Confirm Spline background and other page layout remain unchanged.
