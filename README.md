# Splice Playground
> **Make your own mutant — an AI-powered in silico biology playground for exploring how genomic variants can propagate from DNA to RNA splicing and protein structure.**
<img width="1147" height="719" alt="Image" src="https://github.com/user-attachments/assets/ec2c8f7e-9940-4c04-965e-17bba3bb5bad" />


Splice Playground is a one-year capstone project from the **Department of AI–Software, Gachon University**. The project aims to make modern computational biology more accessible by turning a complex biological workflow — variant selection, DNA sequence editing, splicing prediction, mature mRNA reconstruction, and protein structure comparison — into an interactive web-based learning environment.

This repository is developed as an **educational and research-oriented prototype**. It is not intended for clinical diagnosis, treatment recommendation, or wet-lab replacement. Its purpose is to demonstrate how AI models and curated biological databases can be connected into a rigorous, explainable, and extensible in silico experiment platform.

---

## Project Metadata

| Item | Description |
|---|---|
| Institution | Gachon University, Department of AI–Software |
| Project | Capstone Project / Graduation Project |
| Team | AI Section 1, Team 4 |
| Timeline | 2025.09 – 2026.07 |
| Live demo | https://splice-playground.vercel.app |
| Presentation / idea video | https://youtu.be/GtntQUcu39I |
| Keywords | AI Biology, Computational Biology, SpliceAI, AlphaFold, ColabFold, AlphaGenome, In Silico Biology |

---

## User Interface

<img alt="Splice Playground UI screenshot 1" src="https://github.com/user-attachments/assets/73f9ad0f-6957-40f3-836d-355cd7cc67f0" />
<img alt="Splice Playground UI screenshot 2" src="https://github.com/user-attachments/assets/a3eb2ccf-d59d-4e7d-b063-dfa18a995cfd" />
<img alt="Splice Playground UI screenshot 3" src="https://github.com/user-attachments/assets/43ee55ca-91cb-4604-81b7-9d3309eb0fc1" />

---

## Motivation

Most non-specialists learn the central dogma of molecular biology as a simple sequence:

```text
DNA → RNA → Protein
```

In practice, however, a single nucleotide variant can affect RNA splicing, alter the mature transcript, change the translated amino-acid sequence, and sometimes reshape the three-dimensional protein structure. These effects are difficult to understand through text alone, especially for students whose primary background is computer science or artificial intelligence.

Splice Playground reframes this process as an interactive computational experiment:

```text
Select a disease-associated variant
        ↓
Edit a DNA region under fixed-length sequence rules
        ↓
Predict splice-site changes with a SpliceAI-style model
        ↓
Interpret transcript-level events such as exon exclusion or pseudo-exon insertion
        ↓
Compare normal and user-generated protein structures in 3D
```

The core design goal is to provide a **Scratch-like learning experience for AI biology**: users do not need to manually parse GTF files, genomic coordinates, or protein structure files, but the underlying pipeline remains biologically grounded and traceable.

---

## Core Contributions

1. **End-to-end in silico biology workflow**  
   The project connects disease-associated variant selection, DNA manipulation, splicing prediction, mature mRNA interpretation, protein sequence generation, and 3D structure visualization.

2. **Biologically constrained DNA editing interface**  
   STEP2 uses fixed-length overwrite editing rather than free-form text editing. This preserves genomic coordinate consistency and prevents accidental insertion/deletion artifacts during educational sequence manipulation.

3. **Splicing-aware transcript interpretation**  
   STEP3 distinguishes site-level changes from event-level interpretations, including canonical splice-site changes, exon exclusion, boundary shifts, and pseudo-exon inclusion.

4. **Protein structure comparison workflow**  
   STEP4 compares baseline and user-predicted protein structures using ColabFold-generated or cached structures and visualizes them with Mol*.

5. **Cloud architecture for cost-aware AI biology computation**  
   The system separates lightweight API operations from GPU-based structure prediction, enabling baseline and cached predictions to remain available even when the GPU worker is offline.

---

## Biological Scope and Assumptions

Splice Playground models selected parts of the DNA–RNA–protein chain. To avoid overclaiming, the current implementation follows these assumptions:

- The platform focuses on **educational exploration and hypothesis generation**, not clinical interpretation.
- DNA editing is modeled as **fixed-length substitution/masking**, not arbitrary genome editing.
- `N` in the editor represents an unknown or masked nucleotide for interface-level manipulation; it should not be interpreted as a physical deletion.
- Splicing prediction is treated as a computational estimate and should be validated against transcriptomic or experimental evidence for research use.
- Protein structures generated by ColabFold or related AlphaFold-family tools are predictive models and may not capture all biological states, post-translational modifications, cofactors, or cellular context.

---

## Step-by-Step Workflow

### STEP 1 — Select Mutant
<img width="700" alt="Image" src="https://github.com/user-attachments/assets/09e3bae9-fe99-49d8-8058-ea15eca81f8f" />
<!-- <img width="500" alt="Image" src="https://github.com/user-attachments/assets/fc206c54-27e9-4937-ad2f-d9f91315dfaf" /> -->

Users select a disease or mutation scenario from a curated database. Each entry is linked to a gene, transcript context, representative variant, and educational disease description.

### STEP 2 — Manipulate DNA
<img width="700" alt="Image" src="https://github.com/user-attachments/assets/3773e4e4-9fcc-4e06-ba04-5e6a30323bab" />
<!-- <img width="500" alt="Image" src="https://github.com/user-attachments/assets/83b3740e-9aef-447c-b9c5-f1a4e422ec01" /> -->

Users edit a selected DNA region under a strict fixed-length overwrite policy:

- `A/C/G/T/N` overwrite the current nucleotide.
- Backspace and Delete do not shorten the sequence; they replace the target position with `N`.
- Editing preserves sequence length and coordinate consistency.
- Differences from the reference and disease-associated sequence are highlighted.

This design is intentionally different from a normal text editor. It protects the biological coordinate system while still allowing users to create custom mutant sequences.

### STEP 3 — Mature mRNA
<img width="700" alt="Image" src="https://github.com/user-attachments/assets/00d0987c-dd8a-4229-b8db-b0c16445f1f4" />

The backend predicts how sequence edits affect splice donor and acceptor signals. The result is converted into transcript-level interpretations such as:

- canonical splice-site weakening or strengthening,
- exon exclusion,
- pseudo-exon inclusion,
- boundary shift,
- no major predicted splicing change.

The user sees these outcomes as exon-level visual blocks rather than raw model scores alone.

### STEP 4 — Protein Structure
<!-- <img width="500" alt="Image" src="https://github.com/user-attachments/assets/0bc1acc0-fc99-46ed-8f26-ee7eba891c81" /> -->
<!-- <img width="500" alt="Image" src="https://github.com/user-attachments/assets/e48738a9-9a50-4bac-9fb4-c445678c109a" /> -->
<img width="700" alt="Image" src="https://github.com/user-attachments/assets/c21a0b8a-ad18-419d-93d5-1b66f652c3af" />

The platform translates the interpreted mRNA into a protein sequence and compares the user-generated protein with the baseline protein.

The structure viewer supports:

- normal protein structure,
- user-predicted protein structure,
- overlay comparison,
- structural similarity display,
- reuse of cached or identical structures when available.

<!-- <img width="1147" height="719" alt="Image" src="https://github.com/user-attachments/assets/ed46d192-9727-4e8a-a3f8-c6d6e7d3bcfa" /> -->
<!-- <img width="885" height="729" alt="Image" src="https://github.com/user-attachments/assets/83d3ba04-e397-4cb5-9e98-977f7d6f6ef6" /> -->

---

## System Architecture
<img width="6499" height="1677" alt="Image" src="https://github.com/user-attachments/assets/75adf3b7-4866-45bc-8d6a-58faa3240423" />
<img width="6558" height="2832" alt="Image" src="https://github.com/user-attachments/assets/5afef092-c91f-4e2f-835e-89aa2601186e" />

```text
Frontend                         Public Backend                    GPU Worker
Next.js / React / TypeScript      FastAPI / Python / Docker         ColabFold job runner
Vercel deployment                 AWS EC2 t3 instance               AWS EC2 g5 instance
        │                                  │                                  │
        ├──────────── API requests ───────▶│                                  │
        │                                  ├──── read/write state ───────────▶│
        │                                  │                                  │
        │                                  └──── enqueue structure jobs ─────▶│
        │                                                                     │
        └──────────── structure assets / job status via backend + Supabase ◀──┘
```

### Components

| Layer | Technology | Role |
|---|---|---|
| Frontend | Next.js, React, TypeScript | Interactive UI, DNA editor, STEP visualization, Mol* viewer integration |
| Public backend | FastAPI, Python, Docker | API contract, sequence processing, state management, splicing interpretation |
| Database / storage | Supabase PostgreSQL + Storage | Gene, transcript, variant, state, job, and structure asset persistence |
| GPU worker | AWS EC2 g5 + ColabFold | Asynchronous protein structure prediction |
| Deployment | Vercel + AWS EC2 | Public UI hosting and backend/GPU separation |

The frontend does not directly manipulate biological database records. Genomic coordinate rules, sequence reconstruction, transcript interpretation, and structure job orchestration are centralized in the backend to reduce client-side inconsistency.

---

## Data and Curation Strategy

The long-term goal is to maintain a transparent gene–disease–variant database suitable for educational exploration. The pipeline is designed around the following principles:

1. **Traceability** — every disease or variant entry should point to its source database or publication.
2. **Coordinate consistency** — genomic, transcript, exon, intron, and protein coordinates should be stored with explicit reference genome and transcript identifiers.
3. **Evidence separation** — clinically curated evidence, computational prediction, and educational explanation should not be mixed as if they had the same confidence level.
4. **Extensibility** — the database should be able to incorporate external evidence sources such as ClinVar, GeneBe, Open Targets, and future target–disease association resources.

A key future direction is to use the Open Targets Platform as a reference for systematic target–disease evidence aggregation and prioritization while preserving the project’s educational interface.

---

## Repository Organization

```text
splice-playground/
├─ frontend/                 # Next.js application deployed on Vercel
│  ├─ app/
│  ├─ public/
│  ├─ package.json
│  └─ next.config.mjs
│
├─ backend/                  # FastAPI backend, uv project, Docker deployment
│  ├─ app/
│  ├─ pyproject.toml
│  ├─ uv.lock
│  └─ Dockerfile
│
├─ scripts/                  # Data preprocessing and research utilities
│  ├─ pyproject.toml
│  └─ preprocess_*.py
│
├─ shared/                   # Shared biological or API utilities, if separated
│  └─ src/
│
├─ data/                     # Local data workspace; large raw files are not committed
├─ docker-compose.yml
├─ .gitignore
└─ README.md
```

---

## Team Members

| Name | Role | Student ID | GitHub | Email |
| :--: | :--: | :--: | :--: | :--: |
| 강민준 | AI, DB<br>Team Leader | 202434712 | https://github.com/the-martin-kang | mintory20@snu.ac.kr |
| 남윤정 | Frontend | 202334455 | https://github.com/Southernyj | namyj26@naver.com |
| 이정균 | Backend | 202135814 | https://github.com/Junggyun827 | jungun0827@gmail.com |
| 김현우 | PPT 자료조사| 202239868 | https://github.com/hyunw0000 | lukert@gachon.ac.kr |
| 최진범 | PPT 자료조사 | 202239882 | https://github.com/Choijinbum | cjb2030@gachon.ac.kr |

---

## Roadmap

### Short-term

- Strengthen gene–disease–variant database provenance.
- Add clearer evidence labels for curated references versus model predictions.
- Improve STEP2 editing robustness for long intronic regions.
- Expand disease examples while maintaining transcript-coordinate correctness.
- Add documentation for backend API contracts and state transitions.

### Mid-term

- Integrate more systematic external references for target–disease evidence, including Open Targets-style evidence aggregation.
- Add validation pages comparing predicted splicing outcomes with known literature examples or RNA evidence when available.
- Improve protein comparison metrics and visualization of structurally affected regions.

### Long-term: STEP5 Molecular Interaction Simulation
<img width="5645" height="1730" alt="Image" src="https://github.com/user-attachments/assets/4ae7dcbc-cac3-4c65-b686-5da8dbf35d64" />

A planned extension is **STEP5: Molecular Interaction Simulation**. Instead of stopping at protein structure comparison, STEP5 would ask whether the mutant protein preserves, loses, or gains interaction behavior.

Possible questions include:

- Does the mutant protein still bind its expected molecular partner?
- Is the global structure changed while the functional binding site remains intact?
- Is the binding interface disrupted despite a small sequence difference?
- Could the altered protein create abnormal interaction hypotheses relevant to immune or disease mechanisms?

Technically, this step may combine protein structure features, molecular graph representations, MoleculeNet-style benchmarks, and graph neural networks for exploratory binding or interaction prediction. This would remain a hypothesis-generation module rather than a validated biomedical simulator.

---

## Limitations

Splice Playground deliberately separates **what is implemented** from **what is scientifically validated**.

- SpliceAI-style inference is not sufficient for clinical variant classification by itself.
- Protein structure prediction does not guarantee functional correctness.
- Variant effects can be tissue-specific, context-dependent, and influenced by regulatory mechanisms not modeled in the current version.
- The platform currently prioritizes explainability and educational interaction over benchmark-level model comparison.

These limitations are not treated as failures of the project. They define the boundary between an educational in silico playground and a validated biomedical research system.

---

## Selected References

1. Jaganathan, K., Kyriazopoulou Panagiotopoulou, S., McRae, J. F., _et al._ Predicting splicing from primary sequence with deep learning. _Cell_ **176**, 535–548.e24 (2019). https://doi.org/10.1016/j.cell.2018.12.015
2. Hwang, H., Jeon, H., Yeo, N. & Baek, D. Big data and deep learning for RNA biology. _Experimental & Molecular Medicine_ **56**, 1293–1321 (2024). https://doi.org/10.1038/s12276-024-01243-w
3. Avsec, Ž., Latysheva, N., Cheng, J., _et al._ Advancing regulatory variant effect prediction with AlphaGenome. _Nature_ (2026). https://doi.org/10.1038/s41586-025-10014-0
4. Jumper, J., Evans, R., Pritzel, A., _et al._ Highly accurate protein structure prediction with AlphaFold. _Nature_ **596**, 583–589 (2021). https://doi.org/10.1038/s41586-021-03819-2
5. Mirdita, M., Schütze, K., Moriwaki, Y., _et al._ ColabFold: making protein folding accessible to all. _Nature Methods_ **19**, 679–682 (2022). https://doi.org/10.1038/s41592-022-01488-1
6. Wu, Z., Ramsundar, B., Feinberg, E. N., _et al._ MoleculeNet: a benchmark for molecular machine learning. _Chemical Science_ **9**, 513–530 (2018). https://doi.org/10.1039/C7SC02664A
7. Illumina. SpliceAI repository. https://github.com/Illumina/SpliceAI
8. Google DeepMind. AlphaFold v2 inference pipeline. https://github.com/google-deepmind/alphafold
9. Mirdita, M. / sokrypton. ColabFold repository. https://github.com/sokrypton/ColabFold
10. Google DeepMind. AlphaFold 3 inference pipeline. https://github.com/google-deepmind/alphafold3
11. Open Targets Platform documentation. https://platform-docs.opentargets.org/
12. Youngoh Kim, Sun Kim, _et al._ MixingDTA: improved drug–target affinity prediction by extending mixup with guilt-by-association, _Bioinformatics_ **41**, i105–i114 (2025). https://doi.org/10.1093/bioinformatics/btaf238

---

## Project Status

Splice Playground is under active development as a capstone project. The current system demonstrates the feasibility of connecting AI models, biological sequence databases, cloud infrastructure, and molecular visualization into a single educational platform.

The project’s main scientific position is intentionally conservative:

> It does not claim to replace biological experiments.  
> It aims to make the logic of modern computational biology visible, interactive, and extensible.
