Apply this patch at your backend root so only the files below are overwritten.

Included files:
- app/db/repositories/disease_repo.py
- app/db/repositories/snv_repo.py
- app/db/repositories/state_repo.py
- app/schemas/disease.py
- app/services/disease_service.py
- app/services/state_service.py
- app/services/splicing_service.py
- app/services/snv_alleles.py

What this patch does:
- Adds disease visibility/service-step gating fields support
- Adds seed_mode support (apply_alt vs reference_is_current)
- Adds allele_coordinate_system support for SNV display/apply logic
- Keeps region.sequence gene-direction; converts SNV to gene-direction on the fly when needed
- Keeps BRCA1 legacy gene_direction rows working

How to apply from backend root:

    unzip backend_snv_policy_patch_clean.zip -d .

Then restart/redeploy the backend.
