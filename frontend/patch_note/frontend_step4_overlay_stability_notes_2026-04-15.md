STEP4 frontend patch notes (2026-04-15)

What was fixed
- Prevented Mol* flicker while ColabFold job polling runs.
- Kept the normal structure visible while the job is queued/running instead of constantly recreating the viewer.
- Preserved structure URLs by structure_asset_id so repeated signed-url refreshes do not remount Mol*.
- Fixed view-mode reset bug: when the user structure becomes available, the page now stays in overlay mode instead of being forced back to single-user view.
- Added a clearer ColabFold progress banner in Translation Summary.
- Added browser-side TM-align overlay comparison using Mol* package APIs.
- Promoted 3D structural similarity (TM-score based) to the main KPI, while still keeping AA similarity visible as secondary context.

Files changed
- app/components/MolstarViewer.tsx
- app/components/Step4Protein.tsx

Behavior after patch
- While ColabFold is queued/running: the normal structure stays rendered, no blinking/remount loop.
- When the user structure arrives: the view automatically switches to overlay compare.
- Overlay compare uses green for normal and red for generated structure.
- Structure similarity shown in UI is based on browser-side TM-align, not sequence-string similarity.
