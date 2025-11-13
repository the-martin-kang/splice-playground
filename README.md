# splice-playground
- Institution: Gachon University, Department of AI–Software
- Project: Capstone Project (Graduation Project)
- Team: AI Section 1, Team 4
- Timeline: 2025–2026

## Team Members
| Name |      Role       | Github | Email |
| :--: | :-------------: | :----- | :---- |
| 강민준  |       AI        |        |       |
| 김현우  |       AI        |        |       |
| 남윤정  | frontend, UX&UI |        |       |
| 이정균  |     backend     |        |       |
| 최진범  |       AI        |        |       |


## Overview
```mermaid
flowchart LR
  %% ===== LAYOUT =====
  %% Left: User  |  Right: Cloud (Reverse proxy -> Gateway -> Microservices -> Queue/Workers -> Storage)
  %% Bottom: Dev/CI/CD

  %% USER
  subgraph U[User]
    BR[Browser (React/Next.js)\nPlayground UI]
  end

  BR -- HTTPS --> RP

  %% CLOUD
  subgraph C[AWS/GCP/K8s Cluster]
    RP[Nginx / Traefik\nReverse Proxy]

    subgraph GW[Django Gateway\nAuth · Admin · Classroom · REST & WebSocket]
      DG[Django + DRF\nSSE/WebSocket Hub]
    end

    RP --> DG

    %% MICROSERVICES (Python)
    subgraph SVC[Python Microservices]
      SP[FastAPI — Splicing API\n(pre-mRNA edit → SpliceAI Δscore)]
      CD[FastAPI — Coding API\n(CDS edit → ORF/PTC/NMD)]
      FD[FastAPI — Fold API\n(Protein/Complex → AF3/ColabFold)]
      DG --> SP
      DG --> CD
      DG --> FD
    end

    %% QUEUE
    Q[(Redis/RabbitMQ\nJob Queue)]
    SP -->|enqueue| Q
    CD -->|enqueue| Q
    FD -->|enqueue| Q

    %% WORKERS
    subgraph WK[Workers (Celery/RQ)]
      W1[SpliceAI Inference\n(PyTorch/TF • 1D dilated conv)]
      W2[ORF/NMD Analyzer\n(translation rules)]
      W3[Fold Runner\n(ColabFold/AF3 • GPU)]
    end

    Q --> W1
    Q --> W2
    Q --> W3

    %% STORAGE / CACHE
    R[(Redis Cache)\nper-base scores]
    P[(PostgreSQL)\nUsers · Classes · Jobs · Results]
    O[(S3/MinIO)\nΔscore JSON · PDB/mmCIF · thumbnails]

    DG --> P
    DG --> R
    W1 --> R
    W1 --> O
    W2 --> O
    W3 --> O

    %% STATUS STREAM
    DG <-- SSE/WebSocket --> BR
  end

  %% DEV / CI-CD
  subgraph D[Developer & CI/CD]
    GH[GitHub Repo\nsplice-playground]
    CI[Jenkins / GitHub Actions\nBuild & Deploy]
  end

  GH -- webhook --> CI
  CI -- docker image / rollout --> RP
  CI -- deploy --> SVC
  CI -- migrate --> P

  %% OPTIONAL MONITORING
  subgraph M[Observability]
    MO[Prometheus/Grafana]
    LG[ELK/Opensearch Logs]
  end
  SVC --> MO
  WK --> MO
  RP --> LG

  %% STYLES
  classDef box fill:#fff,stroke:#555,stroke-width:1px;
  classDef proxy fill:#E3F2FD,stroke:#1565C0,stroke-width:1px;
  classDef gate fill:#FFF8E1,stroke:#FF8F00,stroke-width:1px;
  classDef svc fill:#E8F5E9,stroke:#2E7D32,stroke-width:1px;
  classDef infra fill:#ECEFF1,stroke:#607D8B,stroke-width:1px,stroke-dasharray:4 3;
  classDef store fill:#FAFAFA,stroke:#9E9E9E,stroke-width:1px,stroke-dasharray:4 3;

  class BR,GH,CI,MO,LG box
  class RP proxy
  class DG gate
  class SP,CD,FD svc
  class Q,R,P,O,WK infra
```
