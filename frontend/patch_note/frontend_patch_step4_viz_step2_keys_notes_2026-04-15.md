# Frontend patch notes — 2026-04-15

## Included fixes

### 1) STEP4 structure display on Vercel
- Replaced the custom runtime JS bootstrap path in `MolstarViewer.tsx` with a local iframe-based Mol* viewer page.
- Added `public/vendor/molstar/index.html` and `public/vendor/molstar/favicon.ico` so Vercel can serve a self-contained viewer entrypoint.
- The iframe receives the signed structure URL and format through query parameters and shows a loading overlay while the viewer loads.

### 2) Remove “Built with Spline” branding from background
- Removed the live Spline iframe from `app/layout.tsx`.
- Replaced it with a local static background image (`/images/background.png`) plus gradient overlays.
- This fully removes the Spline watermark from the app without requiring runtime Spline embed.

### 3) STEP2 keyboard hardening
- Kept the existing two-panel STEP2 layout.
- Preserved backspace/delete and valid overwrite characters.
- Explicitly blocked keys that were causing editor corruption, including:
  - Shift
  - Arrow keys
  - Home / End / PageUp / PageDown
  - Tab / Enter / Escape / Insert
  - other non-ACGTN single-key input
- Still allows common clipboard shortcuts: Ctrl/Cmd + A/C/V/X.

## Files changed
- `app/layout.tsx`
- `app/components/MolstarViewer.tsx`
- `app/components/DNAManipulator.tsx`
- `public/vendor/molstar/index.html`
- `public/vendor/molstar/favicon.ico`
