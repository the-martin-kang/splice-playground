# splice-playground
- Institution: Gachon University, Department of AI–Software
- Project: Capstone Project (Graduation Project)
- Team: AI Section 1, Team 4
- Timeline: 2025.9–2026.7

## Team Members
| Name |      Role       | Student ID |               Github               |        Email         |
| 강민준  | AI<br>Team Leader | 202434712  | https://github.com/the-martin-kang | joontory20@naver.com |
| 최진범  |    frontend       | 202239882 | https://github.com/Choijinbum | cjb2030@gachon.ac.kr |
| 남윤정  |    frontend     | 202334455  |                                    |  namyj26@naver.com   |
| 이정균  |     backend     | 202135814  | https://github.com/Junggyun827 | jungun0827@gmail.com |
| 김현우  |    backend     | 202239868  | https://github.com/hyunw0000  | lukert@gachon.ac.kr  |


## Overview
- 프론트 : next.js → vercel에 배포(호스팅)
- 백엔드 : fastapi → AWS에 Docker로
- DB : supabase

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
├─ data/                  # FASTA data(미정..)
│   └─
│
├─ docker-compose.yml        # 로컬에서 한번에 돌릴 때
├─ .gitignore
└─ README.md
```
