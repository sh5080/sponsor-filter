FROM python:3.10-slim

# 기본 환경 변수 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 설치 (Tesseract 및 한국어 언어팩 포함)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-kor \
    libgl1-mesa-glx \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 테서렉트 언어 데이터 복사
COPY tessdata /usr/share/tesseract-ocr/4.00/tessdata/

# 애플리케이션 코드 복사
COPY app ./app
COPY .env .

# 캐시 디렉토리 생성
RUN mkdir -p /app/cache && chmod 777 /app/cache

# 포트 노출
EXPOSE 8000

# 실행 명령
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 