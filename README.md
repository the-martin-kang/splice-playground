# splice-playground
- Institution: Gachon University, Department of AI–Software
- Project: Capstone Project (Graduation Project)
- Team: AI Section 1, Team 4
- Timeline: 2025.9–2026.7
- Idea: https://youtu.be/jHdRVvbMIxs

## User Interface
<img width="10799" height="6728" alt="Image" src="https://github.com/user-attachments/assets/73f9ad0f-6957-40f3-836d-355cd7cc67f0" />
<img width="7024" height="1926" alt="Image" src="https://github.com/user-attachments/assets/a3eb2ccf-d59d-4e7d-b063-dfa18a995cfd" />
<img width="7656" height="1947" alt="Image" src="https://github.com/user-attachments/assets/43ee55ca-91cb-4604-81b7-9d3309eb0fc1" />

## Team Members
| Name |         Role          | Student ID |               Github               |        Email         |
| :--: | :-------------------: | :--------: | :--------------------------------: | :------------------: |
| 강민준  | AI, DB<br>Team Leader | 202434712  | https://github.com/the-martin-kang | joontory20@naver.com |
| 남윤정  |       frontend        | 202334455  |   https://github.com/Southernyj    |  namyj26@naver.com   |
| 이정균  |        backend        | 202135814  |   https://github.com/Junggyun827   | jungun0827@gmail.com |
| 김현우  |          PPT          | 202239868  |    https://github.com/hyunw0000    | lukert@gachon.ac.kr  |
| 최진범  |          PPT          | 202239882  |   https://github.com/Choijinbum    | cjb2030@gachon.ac.kr |
 
 

## Overview
- 프론트 : next.js → vercel에 배포(호스팅)
- 백엔드 : fastapi → AWS에 Docker로
- DB : supabase

### Github repo

```
splice-playground/        # GitHub 레포 하나
├─ frontend/              # Next.js (Vercel이 보는 폴더)
│   ├─ package.json
│   ├─ next.config.mjs
│   └─ ...
│
├─ backend/               # FastAPI + uv + Docker
│   ├─ pyproject.toml
│   ├─ uv.lock
│   ├─ app/
│   └─ Dockerfile
│
├─ scripts/               # 데이터 전처리/연구용 uv 프로젝트
│   ├─ pyproject.toml
│   └─ preprocess_*.py
│
├─ shared/                # backend & scripts에서 같이 쓸 라이브러리 (나중에)
│   ├─ pyproject.toml
│   └─ src/splice_shared/
│
├─ data/                  # FASTA, GTF data(실제 데이터는 전처리 코드에서 링크로만 첨부)
│   └─
│
├─ docker-compose.yml        # 로컬에서 한번에 돌릴 때
├─ .gitignore
└─ README.md
```

### Reference
1. Jaganathan K, Kyriazopoulou Panagiotopoulou S, McRae JF, _et al._ Predicting Splicing from Primary Sequence with Deep Learning. _Cell_ **176(3),** 535-548.e24. (2019). [https://doi.org/10.1016/j.cell.2018.12.015](https://doi.org/10.1016/j.cell.2018.12.015)
2. Avsec, Ž., _et al._ AlphaGenome: advancing regulatory variant effect prediction with a unified DNA sequence model. _bioRxiv_ **20,** 25-06 (2025). [https://doi.org/10.1101/2025.06.25.661532](https://doi.org/10.1101/2025.06.25.661532)
3. Jumper, J., Evans, R., Pritzel, A. et al. Highly accurate protein structure prediction with AlphaFold. _Nature_ **596**, 583–589 (2021). [https://doi.org/10.1038/s41586-021-03819-2](https://doi.org/10.1038/s41586-021-03819-2)
4. Mirdita, M., Schütze, K., Moriwaki, Y. et al. ColabFold: making protein folding accessible to all. _Nat Methods_ **19**, 679–682 (2022). [https://doi.org/10.1038/s41592-022-01488-1](https://doi.org/10.1038/s41592-022-01488-1)
5. Illumina. SpliceAI (GitHub repository). https://github.com/Illumina/SpliceAI
6. Google DeepMind. AlphaFold v2 inference pipeline (GitHub repository). https://github.com/google-deepmind/alphafold
7. Mirdita, M. (sokrypton). ColabFold (GitHub repository). https://github.com/sokrypton/ColabFold
8. Google DeepMind. AlphaFold 3 inference pipeline (GitHub repository).  https://github.com/google-deepmind/alphafold3
