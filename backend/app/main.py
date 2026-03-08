import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 1. 라우터 임포트 (경로 확인: v1에 새로 만든 splicing 사용)
from app.api.v1.router import api_router
from app.api.v1 import splicing  # ← 이 부분이 중요합니다!

# 2. DB 및 모델 임포트
from app.core.database import engine, Base
# 새로운 테이블들이 생성되도록 user_state 등 누락된 모델이 있다면 추가하세요.
from app.models import disease, gene, disease_representative_snv, region, user_state

# 서버 시작 시 테이블 생성
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 설정
current_file_path = os.path.dirname(os.path.realpath(__file__))
static_dir = os.path.join(current_file_path, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 3. 라우터 등록
# 기존 v1 라우터 등록
app.include_router(api_router, prefix="/api/v1")

# 신규 Splicing 라우터 등록 (기존 /api/splicing 대신 /api/v1/splicing 권장)
app.include_router(splicing.router, prefix="/api/v1/splicing", tags=["splicing"])

@app.get("/")
def root():
    return {
        "message": "Genomics Disease API is running",
        "docs": "/docs"
    }