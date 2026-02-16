FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# C extension 빌드 대비 (cc/gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# uv는 pip 설치 대신 공식 이미지에서 "버전 pin"해서 바이너리 복사 (best practice)
COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /uvx /bin/

WORKDIR /app

# Python 버전 고정 파일이 있으면 같이 복사
COPY pyproject.toml uv.lock .python-version ./

# lockfile 기반 설치 + system python 3.12 강제 + python 자동 다운로드 금지
ENV UV_NO_DEV=1
RUN uv sync --locked --python python3.12 --no-python-downloads

COPY app ./app
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
