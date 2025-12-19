```
backend/
├─ app/
│  ├─ main.py              # FastAPI 앱 시작점 (엔트리 포인트)
│  │                       # → 여기서 FastAPI() 만들고 라우터(include_router) 모은다
│  │
│  ├─ api/                 # URL 엔드포인트(라우터) 모음
│  │  ├─ __init__.py
│  │  └─ v1/
│  │     ├─ __init__.py
│  │     ├─ sequences.py   # 예: 서열 관련 API (/predict, /sequence 등)
│  │     └─ auth.py        # 예: 로그인/회원 관련 API
│  │
│  ├─ schemas/             # Pydantic 스키마 (입출력 데이터 정의)
│  │  ├─ __init__.py
│  │  ├─ sequences.py      # 요청/응답용 모델 (SequenceRequest, PredictionResult 등)
│  │  └─ users.py          # UserCreate, UserLogin, UserInfo 등
│  │
│  ├─ services/            # 핵심 로직 (비즈니스 로직, ML 호출 등)
│  │  ├─ __init__.py
│  │  └─ splicing.py       # SpliceAI/SpliceTransformer 등 모델 호출/전처리 함수
│  │                       # 예: run_splice_model(sequence: str) -> Prediction
│  │
│  ├─ db/                  # DB, Supabase 연동 관련
│  │  ├─ __init__.py
│  │  └─ supabase.py       # Supabase 클라이언트 생성, 쿼리 함수 모음
│  │                       # 예: save_prediction(...), get_user(...), list_jobs(...)
│  │
│  ├─ core/                # 공통 설정, 유틸, 보안 등
│  │  ├─ __init__.py
│  │  ├─ config.py         # 환경변수, 설정값 (BASE_URL, DB_URL, API_KEYS 등)
│  │  └─ security.py       # JWT 토큰, 비밀번호 해시 등 (필요하면)
│  │
│  └─ utils/               # 자잘한 유틸 함수들
│     ├─ __init__.py
│     └─ parsing.py        # FASTA 파싱, 염기서열 전처리 함수 등
│
├─ tests/                  # 백엔드 테스트 코드 (나중에라도 분리해두면 좋음)
│  └─ test_sequences.py
│
├─ requirements.txt        # 백엔드 파이썬 라이브러리 목록
# 또는 pyproject.toml      # poetry/uv 같은 툴 쓸 때
│
└─ Dockerfile              # 이 폴더 기준으로 백엔드 도커 이미지 빌드
```