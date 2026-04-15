Frontend patch: STEP2 two-panel editor + dual diff highlighting, STEP3 pseudoexon visualization fix.

Changes
- STEP2 DNAManipulator now shows exactly two sequence panes: Reference and Edited.
- Edited pane keeps fixed-length overwrite behavior but uses a highlighted overlay textarea so diff positions are highlighted in both panes.
- Removed the extra disease-seed and edit-result panes from STEP2 while preserving restore controls.
- STEP3 MatureMRNA now distinguishes pseudoexon insertion from exon exclusion.
- PSEUDO_EXON events render an inserted amber pseudoexon block between flanking exons instead of striking through those exons.
- EXON_EXCLUSION events continue to render excluded exons with dashed red/strike-through styling.
