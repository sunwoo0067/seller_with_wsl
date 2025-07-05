# Python 3.12 기반 이미지
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 파일 복사
COPY requirements.txt .

# Python 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY dropshipping/ ./dropshipping/
COPY tests/ ./tests/
COPY .env.example ./.env.example

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV ENV=production

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 포트 노출
EXPOSE 8000

# 기본 실행 명령 (API 서버)
CMD ["python", "-m", "dropshipping.api.main"]