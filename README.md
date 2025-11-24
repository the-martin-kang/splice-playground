# splice-playground
- Institution: Gachon University, Department of AI–Software
- Project: Capstone Project (Graduation Project)
- Team: AI Section 1, Team 4
- Timeline: 2025.9–2026.7

## Team Members
| Name |      Role       | Student ID |               Github               |        Email         |
| :--: | :-------------: | :--------: | :--------------------------------: | :------------------: |
| 강민준  | AI<br>Team Leader | 202434712  | https://github.com/the-martin-kang | joontory20@naver.com |
| 김현우  |    frontend     | 202239868  |                                    | lukert@gachon.ac.kr  |
| 남윤정  |    frontend     | 202334455  |                                    |  namyj26@naver.com   |
| 이정균  |     backend     | 202135814  |                                    | jungun0827@gmail.com |
| 최진범  |     backend     | 202239882  |                                    | cjb2030@gachon.ac.kr |


## Overview
```
splice-playground/
│
├─ frontend/                 # Next.js (화면)
│   ├─ app/ or pages/
│   ├─ components/
│   ├─ public/
│   ├─ package.json
│   └─ next.config.js
│
├─ backend/                  # FastAPI (서버)
│   ├─ app/
│   │   ├─ main.py
│   │   ├─ api/             # 라우터(주소)
│   │   ├─ services/        # 로직(SpliceAI 호출 등)
│   │   ├─ models/          # DB/데이터 모델
│   │   └─ core/            # 설정, utils
│   ├─ requirements.txt or pyproject.toml
│   └─ Dockerfile
│
├─ shared/                   # 프론트/백엔드가 같이 쓰는 것
│   ├─ types/               # 공통 타입/스키마
│   └─ constants/
│
├─ docs/                     # 문서(설명, 설계, 회의록)
│   ├─ architecture.md
│   ├─ api_spec.md
│   └─ roadmap.md
│
├─ scripts/                  # 데이터 전처리/실험용 스크립트
│   └─ preprocess_ensembl.py
│
├─ data/                  # FASTA data
│   └─
│
├─ docker-compose.yml        # 로컬에서 한번에 돌릴 때
├─ .gitignore
└─ README.md
```
