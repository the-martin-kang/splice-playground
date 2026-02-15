<<<<<<< HEAD
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",        # 로컬 프론트 개발용
        "https://your-app.vercel.app",  # 배포된 Vercel 도메인
    ],
=======
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 내부 모듈 임포트
from app.api.v1.router import api_router
from app.core.database import engine, Base
# 모델들을 임포트해야 Base.metadata.create_all이 모든 테이블을 인식하여 생성합니다.
from app.models import disease, gene, disease_representative_snv, region

# 서버 시작 시 테이블 생성 (이미 존재하면 건너뜁니다)
Base.metadata.create_all(bind=engine)

# FastAPI 인스턴스 생성
app = FastAPI(
    title="Genomics Disease API",
    description="Disease, Gene, SNV, and Sequence Region Management API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
>>>>>>> backend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

<<<<<<< HEAD
@app.get("/health")
def health():
    return {"ok": True}
=======
# 정적 파일 설정 (질병 이미지용)
current_file_path = os.path.dirname(os.path.realpath(__file__))
static_dir = os.path.join(current_file_path, "static")

if not os.path.exists(static_dir):
    # 폴더가 없으면 에러 방지를 위해 생성하거나 경고 출력
    os.makedirs(static_dir, exist_ok=True)
    print(f"📢 알림: 정적 파일 경로를 새로 생성했습니다: {static_dir}")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 라우터 등록 (v1 통합 라우터 사용)
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def root():
    return {
        "message": "Genomics Disease API is running",
        "docs": "/docs"
    }
>>>>>>> backend
