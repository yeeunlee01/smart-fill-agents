FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# docx → PDF 변환용 LibreOffice(Writer) + 한글 폰트(나눔)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 앱 소스
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
