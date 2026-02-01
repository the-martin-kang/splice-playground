# 1) 런타임 이미지 선택
FROM python:3.12-slim

# 2) 기본 환경 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3) 작업 디렉토리
WORKDIR /app

# 4) uv 바이너리 복사 (공식 권장)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 5) 의존성 파일만 먼저 복사 (캐시 활용)
COPY pyproject.toml uv.lock ./

# 6) prod 의존성 설치
RUN uv sync --frozen --no-dev

# 7) venv PATH
ENV PATH="/app/.venv/bin:${PATH}"

# 8) 앱 코드 복사
COPY app ./app

# 9) 포트
EXPOSE 8000

# 10) 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]