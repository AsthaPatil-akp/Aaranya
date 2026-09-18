FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    APP_ENV=production \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DATA_DIR=/data \
    SQLITE_PATH=/data/darukaa.sqlite \
    CHROMA_PATH=/data/chroma \
    KNOWLEDGE_DIR=/app/knowledge \
    PDF_DIR=/data/pdfs \
    SOURCE_DIR=/app/knowledge/sources \
    HF_HOME=/opt/huggingface \
    TRANSFORMERS_CACHE=/opt/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        g++ \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY backend /app/backend
COPY knowledge /app/knowledge
COPY scripts/start.sh /app/scripts/start.sh
RUN chmod +x /app/scripts/start.sh \
    && mkdir -p /data/chroma /data/pdfs

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1

CMD ["/app/scripts/start.sh"]
