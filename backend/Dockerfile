# Pin to Debian bookworm for more stable apt packages (python:3.12-slim may track Debian testing).
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# (Optional) curl is handy for local debugging inside the container.
# OCR: install Tesseract + English, and ensure Vietnamese traineddata exists (download fallback).
RUN set -eux; \
    apt-get update -o Acquire::Retries=5; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-dejavu-core \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils; \
    # Vietnamese pack can be missing in some repos/images; install if available.
    (apt-get install -y --no-install-recommends tesseract-ocr-vie || true); \
    # Ensure ENG/VIE traineddata exist (fallback: download from official tessdata_fast).
    # NOTE: Some Debian builds don't support `tesseract --print-tessdata-dir`, so we locate tessdata via dpkg.
    TESSDATA_FILE="$(dpkg -L tesseract-ocr-eng | grep -m1 'tessdata/eng\.traineddata' || true)"; \
    TESSDATA_DIR="$(dirname "$TESSDATA_FILE" 2>/dev/null || true)"; \
    if [ -z "$TESSDATA_DIR" ] || [ "$TESSDATA_DIR" = "." ]; then \
      TESSDATA_DIR="/usr/share/tesseract-ocr/5/tessdata"; \
    fi; \
    mkdir -p "$TESSDATA_DIR"; \
    if [ ! -f "$TESSDATA_DIR/eng.traineddata" ]; then \
      curl -L --retry 5 --retry-delay 2 \
        https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata \
        -o "$TESSDATA_DIR/eng.traineddata"; \
    fi; \
    if [ ! -f "$TESSDATA_DIR/vie.traineddata" ]; then \
      curl -L --retry 5 --retry-delay 2 \
        https://github.com/tesseract-ocr/tessdata_fast/raw/main/vie.traineddata \
        -o "$TESSDATA_DIR/vie.traineddata"; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# Copy both requirement sets (core + semantic RAG extras)
COPY requirements.txt requirements.semantic.txt ./

# Install core deps + semantic RAG deps (faiss-cpu, openai, ...)
RUN pip install --no-cache-dir -r requirements.txt -r requirements.semantic.txt

COPY . .

RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["bash", "/app/start.sh"]
