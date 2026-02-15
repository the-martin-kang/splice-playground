```mermaid
erDiagram
    DISEASE {
        TEXT disease_id PK
        TEXT disease_name
        TEXT description
        TEXT image_path
    }

    GENE {
        TEXT gene_id PK
        TEXT gene_symbol
        TEXT chromosome
        CHAR strand
        INT length
        INT exon_count
        TEXT canonical_transcript_id
        TEXT canonical_source
        TEXT source_version
    }

    DISEASE_GENE {
<<<<<<< HEAD
        TEXT disease_id PK, FK
        TEXT gene_id PK, FK
=======
        TEXT disease_id FK
        TEXT gene_id FK
>>>>>>> backend
    }

    DISEASE_REPRESENTATIVE_SNV {
        TEXT disease_id PK, FK
        TEXT gene_id FK
        INT pos_gene0
        CHAR ref
        CHAR alt
        TEXT note
    }

    REGION {
        TEXT region_id PK
        TEXT gene_id FK
        TEXT region_type
        INT region_number
        INT gene_start_idx
        INT gene_end_idx
        INT length
        TEXT sequence
        INT cds_start_offset
        INT cds_end_offset
    }

    BASELINE_RESULT {
<<<<<<< HEAD
        TEXT gene_id PK, FK
        TEXT step PK
=======
        TEXT gene_id FK
        TEXT step
>>>>>>> backend
        TEXT model_version
        JSONB result_payload
    }

    SNV_RESULT {
<<<<<<< HEAD
        TEXT disease_id PK, FK
        TEXT step PK
=======
        TEXT disease_id FK
        TEXT step
>>>>>>> backend
        TEXT model_version
        JSONB result_payload
        JSONB delta_payload
    }

    USER_STATE {
        UUID state_id PK
        TEXT disease_id FK
        UUID parent_state_id FK
        JSONB applied_edit
        TIMESTAMPTZ created_at
    }

    USER_STATE_RESULT {
<<<<<<< HEAD
        UUID state_id PK, FK
        TEXT step PK
=======
        UUID state_id FK
        TEXT step
>>>>>>> backend
        TEXT model_version
        JSONB result_payload
        JSONB delta_payload
    }

<<<<<<< HEAD
    STRUCTURE_JOB {
        UUID job_id PK
        UUID state_id FK
        TEXT provider
        TEXT status
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TEXT external_job_id
        JSONB result_payload
        TEXT error_message
    }

    GENE ||--o{ REGION : has

    DISEASE ||--o{ DISEASE_GENE : maps
    GENE ||--o{ DISEASE_GENE : maps

    DISEASE ||--|| DISEASE_REPRESENTATIVE_SNV : has
    GENE ||--o{ DISEASE_REPRESENTATIVE_SNV : caused_by

    GENE ||--o{ BASELINE_RESULT : caches
    DISEASE ||--o{ SNV_RESULT : caches

    DISEASE ||--o{ USER_STATE : spawns
    USER_STATE ||--o{ USER_STATE : derives
    USER_STATE ||--o{ USER_STATE_RESULT : caches

    USER_STATE ||--o{ STRUCTURE_JOB : runs
=======
    DISEASE ||--o{ DISEASE_GENE : links
    GENE ||--o{ DISEASE_GENE : links

    DISEASE ||--|| DISEASE_REPRESENTATIVE_SNV : has
    GENE ||--o{ DISEASE_REPRESENTATIVE_SNV : contains

    GENE ||--o{ REGION : has

    GENE ||--o{ BASELINE_RESULT : produces
    DISEASE ||--o{ SNV_RESULT : produces

    DISEASE ||--o{ USER_STATE : spawns
    USER_STATE ||--o{ USER_STATE_RESULT : yields
>>>>>>> backend
```