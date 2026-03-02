# syntax=docker/dockerfile:1.7
# Python 3.11 currently has the most predictable wheel coverage for FAISS + scientific stack.
ARG PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim-bookworm

FROM ${PYTHON_BASE_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

# Runtime-only system dependencies for OCR/PDF and plotting.
RUN set -eux; \
    apt-get update -o Acquire::Retries=5; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      fonts-dejavu-core \
      fonts-noto-core \
      libfreetype6 \
      libjpeg62-turbo \
      liblcms2-2 \
      libopenjp2-7 \
      libpng16-16 \
      libtiff6 \
      libwebp7 \
      libxml2 \
      libxslt1.1 \
      poppler-utils \
      tesseract-ocr \
      tesseract-ocr-eng \
      tesseract-ocr-vie; \
    rm -rf /var/lib/apt/lists/*

FROM base AS builder

# Tools only needed while installing (avoid carrying into runtime image).
RUN set -eux; \
    apt-get update -o Acquire::Retries=5; \
    apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      pkg-config; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.semantic.txt ./

# Install to a dedicated virtualenv for clean copy into runtime image.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN --mount=type=cache,target=/root/.cache/pip \
    set -eux; \
    pip install --upgrade pip setuptools wheel; \
    pip install --prefer-binary --retries 10 -r requirements.txt -r requirements.semantic.txt

FROM base AS runtime

ENV PATH="/opt/venv/bin:${PATH}"

COPY --from=builder /opt/venv /opt/venv
COPY . .
COPY docker/run_app_script.sh /usr/local/bin/run_app_script.sh
COPY docker/start_backend.sh /usr/local/bin/start_backend.sh
COPY docker/start_worker.sh /usr/local/bin/start_worker.sh

RUN chmod +x \
    /app/start.sh \
    /app/worker_start.sh \
    /usr/local/bin/run_app_script.sh \
    /usr/local/bin/start_backend.sh \
    /usr/local/bin/start_worker.sh

EXPOSE 8000

# Compose should override with /usr/local/bin/start_backend.sh or /usr/local/bin/start_worker.sh.
CMD ["/usr/local/bin/start_backend.sh"]
