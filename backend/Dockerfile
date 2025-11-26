# 1) 런타임 이미지 선택 (prod 용이면 slim 계열이 보통 무난)
FROM python:3.11-slim AS base

# 2) 기본 환경 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3) uv 설치에 필요한 도구들 설치 (curl 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4) uv 설치
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# uv가 /root/.local/bin 에 설치되기 때문에 PATH에 추가
ENV PATH="/root/.local/bin:${PATH}"

# 5) 작업 디렉토리 설정
WORKDIR /app

# 6) 의존성 파일만 먼저 복사 (캐시 활용)
COPY pyproject.toml uv.lock ./

# 7) prod 용 의존성 설치 (.venv 생성)
# --frozen : uv.lock 기준으로 설치
# --no-dev : dev 의존성은 제외 (테스트용 패키지 제외)
RUN uv sync --frozen --no-dev

# 8) .venv를 기본 PATH에 추가 (이후 python/uvicorn 등이 여기에서 실행됨)
ENV PATH="/app/.venv/bin:${PATH}"

# 9) 실제 앱 코드 복사
COPY app ./app

# 10) 컨테이너에서 열어줄 포트
EXPOSE 8000

# 11) 컨테이너 시작 시 FastAPI 서버 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]