# STEP4 baseline fix patch (2026-03-13)

## What this fixes

1. **Wrong CDS cDNA coordinates in `protein_reference`**
   - Root cause: `resolve_transcript_reference_bundle()` trusted Ensembl `Translation.start/end` values as if they were cDNA coordinates.
   - In practice, for the affected transcripts these were genomic-scale coordinates, so rows were written with impossible values such as BRCA1 `43045678..43124096` instead of cDNA-relative positions.
   - Fix: cDNA CDS start/end are now validated against the actual cDNA/CDS strings, and when needed are recovered by unique subsequence search of `cds_seq` inside `cdna_seq`.

2. **Arbitrary RefSeq xref choice**
   - Root cause: xref parsing previously picked the first RefSeq RNA/protein accession returned by Ensembl, even when that accession corresponded to a different isoform.
   - Fix: the ingest pipeline now collects all RefSeq candidate IDs and selects only the accession whose fetched sequence exactly matches the chosen Ensembl cDNA/protein sequence.
   - If no exact RefSeq candidate exists, the row stays conservative instead of writing an arbitrary mismatched RefSeq ID.

3. **Better validation diagnostics**
   - `validate_db_regions_against_reference()` now reports suggested cDNA CDS coordinates when the stored coordinates are invalid but the CDS can be recovered uniquely from the mRNA.

## Files changed

- `app/services/step4_sources.py`
- `app/services/step4_validation.py`

## Expected effect after re-running ingest

- `db_region_ok` should become `true` for the genes whose `canonical_mrna_seq` already matches your DB exon assembly.
- Genes that previously failed only because of bad CDS coordinates should move out of `review_required`.
- Genes that previously failed because of a wrong RefSeq isoform choice (e.g. BRCA1-like cases) should now resolve to an exact RefSeq match when one exists.
- Automated structure ingest should start for rows whose final validation status becomes a pass status.

## Re-run instructions

From your backend root:

```bash
uv run scripts/ingest_step4_baseline.py
```

To check a single gene after ingest:

```bash
uv run scripts/validate_step4_baseline.py --gene-id BRCA1
```

## Deployment note

This patch changes the local ingest/validation pipeline. The `/api/.../step4-baseline` endpoints read from the DB rows and storage assets.

- If you only re-run the local ingest and do **not** change API behavior, AWS redeploy is **not required** for the data fix itself.
- If you want the deployed repo to exactly match your local repo, redeploy afterward for consistency.
