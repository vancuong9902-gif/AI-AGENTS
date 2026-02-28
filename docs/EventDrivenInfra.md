# Event-driven Infrastructure (RQ/Redis) — Background Indexing + Drift Monitoring

This document describes the event-driven infrastructure added in **v6**:

- **Async queue**: Redis + RQ
- **Background indexing**: embed + index document chunks without blocking request latency
- **Background drift monitoring**: periodic checks for retrieval/policy/learning drift

## 1. Motivation

Several operations in the adaptive learning pipeline are *compute-heavy* and/or *I/O bound*:

1) PDF extraction + chunking  
2) Embedding generation + FAISS indexing  
3) Re-ranking, analytics aggregation, drift diagnostics

A request-response architecture makes these operations appear as spikes in API latency and can cause
timeouts under multi-user concurrency.

We adopt an **event-driven** design by introducing an async queue and workers.

## 2. Components

### 2.1 Redis (broker)
Configured by `REDIS_URL` (default: `redis://localhost:6379/0`).

### 2.2 RQ workers (queues)
We use 3 queues to isolate workloads and avoid head-of-line blocking:

- `index`: embeddings / vector index maintenance
- `monitor`: drift monitoring jobs
- `default`: generic background tasks

### 2.3 App integration
`app/infra/queue.py` provides:
- `enqueue(fn, *args, **kwargs)`
- synchronous fallback when `ASYNC_QUEUE_ENABLED=false`

## 3. Background Indexing

### 3.1 Upload flow
During `/api/documents/upload`:
- if semantic RAG enabled AND `ASYNC_QUEUE_ENABLED=true`:
  - the API enqueues `task_index_document(document_id)` (queue: `index`)
  - returns a `job_id` in the response

Otherwise, indexing runs synchronously (demo-friendly).

### 3.2 Index rebuild
Endpoint:
- `POST /api/jobs/index/rebuild` → enqueues `task_rebuild_vector_index()`

## 4. Drift Monitoring

We compute a composite drift report:
- Retrieval drift: based on `rag_queries` (empty hit rate, avg hits, doc diversity)
- Policy drift: based on `policy_decision_logs` (entropy, oscillation)
- Learning drift: based on `analytics_history` (knowledge slope + dropout risk delta)

Endpoints:
- `POST /api/jobs/drift/check` → enqueue `task_run_drift_check(days=7, ...)`
- `GET /api/jobs/drift/reports` → list stored reports (DB table: `drift_reports`)

## 5. Deployment

### 5.1 docker-compose
We added:
- `redis` service
- `worker` service running `rq worker -u REDIS_URL default index monitor`

### 5.2 Environment variables
Add to `backend/.env`:

```
ASYNC_QUEUE_ENABLED=true
REDIS_URL=redis://redis:6379/0
RQ_DEFAULT_TIMEOUT_SEC=1800
```

## 6. Notes / Safety

- Indexing jobs should run with low concurrency (1 worker) to avoid FAISS file races.
- Drift checks are read-heavy; keep them in `monitor` queue with separate worker capacity if needed.
