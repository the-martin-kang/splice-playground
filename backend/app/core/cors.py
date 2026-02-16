# app/core/cors.py
from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.config import Settings


def setup_cors(app: FastAPI, settings: Settings) -> None:
    """
    CORS 설정
    - 프론트(Next.js/Vercel) → 백엔드(App Runner) 호출을 허용
    - B 방식 이미지(Signed URL)는 결국 브라우저가 supabase storage로 GET 하게 되므로,
      "이미지 URL 자체"는 CORS와 직접 상관없고,
      API 호출(backend)에 대한 CORS만 잘 설정하면 됨.
    """

    # 로컬 개발 기본값(환경변수 미설정 시)
    default_local = ("http://localhost:3000", "http://127.0.0.1:3000")
    allow_origins = list(settings.cors_origins) if settings.cors_origins else list(default_local)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=600,
    )
