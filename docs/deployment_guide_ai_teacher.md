# Deployment Guide – AI Teacher Platform

## Stack
- FastAPI API pods
- Worker pods for heavy AI jobs
- PostgreSQL
- Redis
- Vector DB (FAISS local volume or Chroma server)

## Environment Variables
- `DATABASE_URL`
- `REDIS_URL`
- `OPENAI_API_KEY`
- `OPENAI_CHAT_MODEL`
- `OPENAI_EMBEDDING_MODEL`
- `SEMANTIC_RAG_ENABLED=true`
- `AUTH_ENABLED=true`
- `LOG_LEVEL=INFO`

## Docker Build
```bash
docker compose build backend worker
docker compose up -d postgres redis backend worker
```

## Health + Smoke
```bash
curl -s http://localhost:8000/api/health
curl -s http://localhost:8000/api/v2/teacher-ai/documents/ingest -X POST \
  -H 'Content-Type: application/json' \
  -d '{"document_id":"doc-001","content":"Linear algebra includes vectors, matrices, eigenvalues..."}'
```

## Production Hardening Checklist
1. Enable reverse proxy (Nginx/Traefik) with TLS.
2. Pin worker concurrency and queue retries.
3. Move vector index to persistent volume or managed Chroma.
4. Add migrations for SQL schema in `docs/sql/learning_engine_schema.sql`.
5. Configure centralized logs (ELK/OpenSearch/Grafana Loki).
6. Add OpenTelemetry exporter and dashboards.
