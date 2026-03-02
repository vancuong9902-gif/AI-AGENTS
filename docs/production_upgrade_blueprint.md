# AI Adaptive Learning Platform — Production Upgrade Blueprint

## PHASE 1 — Architecture Overview
- Chọn **modular monolith** (FastAPI) cho giai đoạn hiện tại để giảm độ phức tạp vận hành, giữ khả năng tách service sau này bằng bounded contexts.
- Modules chính: `auth`, `learning`, `assessment`, `ai_orchestration`, `rag`, `analytics`, `platform`.
- Tách rõ lớp: API Router -> Application Services -> Domain Policies -> Infrastructure (DB, queue, vector DB).

## PHASE 2 — Database Schema + Migrations
Schema mục tiêu gồm bảng:
- `roles`, `users`
- `topics`, `questions`
- `exams`, `exam_results`
- `student_profiles`, `mastery_scores`
- `learning_sessions`
- `memory_threads`, `memory_messages` (AI tutor memory)
- `rag_documents`, `rag_chunks`, `rag_retrieval_logs`

Migration strategy:
1. Dùng Alembic revision riêng cho từng bounded context.
2. Tạo index cho cột truy vấn cao tần (`user_id`, `topic_id`, `created_at`).
3. Mọi list endpoints áp dụng pagination (`LIMIT/OFFSET` + `total`).

## PHASE 3 — Adaptive Algorithm Design
Luật cập nhật mastery:
- Correct + response_time < 10s => `+2`
- Correct + response_time >= 10s => `+1`
- Incorrect => `-2`

ELO-like ability update đã được hiện thực tại `backend/app/services/adaptive_engine.py`.
- ability mới = `ability + K * (observed - expected)`
- expected = logistic(ability - difficulty)
- độ khó khuyến nghị kế tiếp dựa trên `ability - difficulty gap`.

## PHASE 4 — AI Agent Orchestration Design
Agents:
- `ContentAgent`: sinh giải thích và học liệu ngắn.
- `AssessmentAgent`: tạo câu hỏi/đề kiểm tra theo mục tiêu.
- `StudentModelAgent`: cập nhật mastery + risk signals.
- `RecommendationAgent`: đề xuất topic/difficulty tiếp theo.
- `MemoryAgent`: ghi/đọc hội thoại + lịch sử học.
- `RAGAgent`: chunk -> embed -> retrieve context.

Text diagram:
`API -> OrchestratorService -> {StudentModelAgent, RAGAgent, ContentAgent, AssessmentAgent, RecommendationAgent} -> MemoryAgent`

Message contract (JSON):
- envelope: `trace_id`, `student_id`, `session_id`, `agent`, `intent`, `payload`, `timestamp`.
- response: `status`, `result`, `error?` (chuẩn hóa error contract).

## PHASE 5 — OpenAPI Specification
OpenAPI v3 được bổ sung tại `backend/openapi/adaptive_learning_openapi_v1.yaml`, gồm các route:
- `POST /auth/register`
- `POST /auth/login`
- `GET /users/me`
- `GET /topics`
- `POST /questions`
- `POST /exams`
- `POST /exams/{id}/submit`
- `GET /progress`
- `POST /ai/chat`
- `POST /ai/agent`

Error model chuẩn:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "fieldErrors": []
  }
}
```

## PHASE 6 — Backend Implementation
Đã bổ sung `AdaptiveEngine` typed service:
- Input typed bằng `LearnerSignal` dataclass.
- Output typed bằng `AdaptiveUpdate` dataclass.
- Có clamp difficulty để giữ miền giá trị an toàn.

## PHASE 7 — Tests
Đã thêm unit tests cho adaptive policy tại:
- `backend/tests/services/test_adaptive_engine.py`

## PHASE 8 — Deployment Configuration
Dùng hiện trạng repo:
- Backend Docker: `backend/Dockerfile`
- Frontend Docker: `frontend/Dockerfile`
- Compose: `docker-compose.yml`
- Env mẫu: `.env.example`
- CI: `.github/workflows/ci.yml`

Khuyến nghị monitoring/logging production:
- Metrics scrape qua Prometheus + dashboard Grafana.
- Structured JSON logs + trace_id correlation ở mọi service boundary.

## PHASE 9 — Project Folder Structure
Đề xuất chuẩn hóa:
- `backend/app/api`
- `backend/app/services`
- `backend/app/domain`
- `backend/app/infra`
- `backend/app/models`
- `backend/app/schemas`
- `backend/openapi`
- `frontend/src/features/*`

## PHASE 10 — README Documentation
Cập nhật README để:
1. Nêu rõ quickstart (docker compose).
2. Nêu kiến trúc module + security defaults.
3. Gắn link OpenAPI + blueprint tài liệu.
4. Chỉ rõ checklist production readiness.

## Self-validation Checklist
- DB schema có `mastery_scores`, `learning_sessions`, `exam_results` để phục vụ adaptive scoring.
- OpenAPI file đúng chuẩn v3.0.3, có auth + error schema.
- Route private yêu cầu bearerAuth trong OpenAPI.
- Unit tests bao phủ luật cộng/trừ mastery + ELO update cơ bản.
- Docker/CI artifacts hiện hữu và được tham chiếu rõ.
