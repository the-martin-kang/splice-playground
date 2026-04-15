This patch resolves the Vercel build error caused by a mismatched pair of files:
- Step4Protein.tsx expected MolstarComputedComparison and MolstarStructureInput
- MolstarViewer.tsx did not export them

It also restores the interactive Spline DNA background using the provided public URL.
Apply from the frontend project root.
