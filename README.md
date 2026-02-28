# AI Learning Agent (Project Skeleton)

Khung project cho đề tài _Cá nhân hoá chương trình học dựa trên AI Agent_.

- **Backend**: FastAPI + Swagger (/docs) + SQLAlchemy + Alembic
- **DB**: Postgres (Docker Compose) hoặc cài local
- **Frontend**: React + Vite (Home tối thiểu)
- **Docs**: Quy ước branch/PR + template báo cáo tuần

## 1) Cấu trúc thư mục

```
.
├─ backend/                 # FastAPI + DB + migrations
├─ frontend/                # React/Vite
├─ docs/                    # quy ước làm việc
├─ docker-compose.yml        # DB + Backend + Frontend (dev)
└─ README.md
```

## 2) Chạy nhanh (khuyến nghị) — Docker Compose (DB + Backend + Frontend)

Tại thư mục root:

```bash
cp .env.example .env
# ✅ Default: OpenAI GPT-oss 20B (openai-gpt-oss-20b)
# Mở file .env và chọn 1 trong các cấu hình dưới đây:
#
# --- (A) OpenAI Cloud ---
#   OPENAI_API_KEY=<sk-...>
#   OPENAI_BASE_URL=
#   OPENAI_CHAT_MODEL=openai-gpt-oss-20b
#   OPENAI_REASONING_EFFORT=none
#   SEMANTIC_RAG_ENABLED=false  # bật true nếu muốn dùng embeddings + FAISS
#
# --- (B) Azure OpenAI ---
#   AZURE_OPENAI_ENDPOINT=https://<resource-name>.openai.azure.com/
#   AZURE_OPENAI_API_KEY=<your azure key>
#   AZURE_OPENAI_API_VERSION=2024-02-15-preview
#   OPENAI_CHAT_MODEL=<azure deployment name>  # ví dụ: openai-gpt-oss-20b
#
# --- (C) MegaLLM (OpenAI-compatible gateway) ---
#   OPENAI_API_KEY=<sk-mega-...>
#   OPENAI_BASE_URL=https://ai.megallm.io/v1
#   OPENAI_CHAT_MODEL=claude-opus-4-5-20251101
#   SEMANTIC_RAG_ENABLED=false  # MegaLLM thường không có embeddings endpoint công khai
#
# --- (D) Alibaba Cloud Model Studio (DashScope) / Qwen (OpenAI-compatible) ---
#   OPENAI_API_KEY=<DASHSCOPE_API_KEY>
#   OPENAI_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
#   OPENAI_CHAT_MODEL=qwen-plus
#   # Qwen3/Qwen3.5 hybrid-thinking models: tắt thinking để ổn định JSON
#   QWEN_ENABLE_THINKING=false
#   # (tuỳ chọn) Nếu muốn dùng embeddings + FAISS
#   SEMANTIC_RAG_ENABLED=true
#   OPENAI_EMBEDDING_MODEL=text-embedding-v3
#
# (tuỳ chọn) Có thể điều khiển:
# - QUIZ_GEN_MODE=auto|llm|offline
# - LESSON_GEN_MODE=auto|llm|offline

docker compose up --build
```

Mở:

- Frontend: http://localhost:5173
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

Frontend có sẵn UI demo:
- **Login giả lập** (chọn Student/Teacher)
- Teacher: **Upload** tài liệu
- Student: **Generate Quiz** → làm bài → xem **Result**
- **Thư viện tài liệu** (list document từ DB)

✅ **B6+ (Learning Path kiểu giáo viên) — có lưu tiến độ**

- Ở trang **Learning Path**, bạn có thể bấm **"Lưu / Tạo plan mới"** để lưu kế hoạch 7 ngày vào DB.
- Checklist nhiệm vụ (✅) và điểm chấm **bài tập tự luận** sẽ **không mất khi refresh**.
- API mới:
  - `GET /api/learning-plans/{user_id}/latest`
  - `POST /api/learning-plans/{plan_id}/tasks/complete`
  - `POST /api/learning-plans/{plan_id}/homework/grade`

> DB mặc định: user/pass `postgres/postgres`, database `ai_agent`, port `5432`.

## 3) Chạy dev local (không dùng container backend/frontend)

### 3.1. Chạy Backend

```bash
cd backend
cp .env.example .env
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt

# (tuỳ chọn) Nếu bạn muốn bật Semantic RAG (FAISS) giống Week1:
# pip install -r requirements.semantic.txt

# chạy migrations để tạo bảng
alembic upgrade head

# chạy server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Mở Swagger:

- http://localhost:8000/docs

Health check:

- http://localhost:8000/api/health

### 3.2. Chạy Frontend

```bash
cd ../frontend
cp .env.example .env
npm install
npm run dev
```

Mở web:

- http://localhost:5173

## 4) Chạy local (không dùng Docker)

- Cài Postgres local và tạo DB `ai_agent`
- Sửa `DATABASE_URL` trong `backend/.env` cho đúng máy bạn

## 5) Quy ước làm việc nhóm

Xem:

- `docs/CONTRIBUTING.md`
- `docs/reports/weekly_template.md`
- `.github/pull_request_template.md`

## 6) Luồng demo tuần 2 (Postman/Swagger)
### 6.0 Semantic RAG (FAISS) — ghép nối từ Week1

Mặc định, RAG sẽ **fallback keyword** (chạy được ngay, không cần thêm deps).

Nếu bạn muốn **semantic search giống Week1** (FAISS + OpenAI embeddings):
- **Docker Compose:** deps semantic đã được cài sẵn trong image backend. Chỉ cần set `OPENAI_API_KEY` trong file `.env` (ở root) rồi `docker compose up --build`.
- **Chạy local (venv):** cài thêm deps: `pip install -r backend/requirements.semantic.txt`.
- Set `OPENAI_API_KEY` trong file `.env` (nằm tại thư mục bạn chạy uvicorn).
- Upload tài liệu (server sẽ cố gắng index ngay)
- Nếu bạn upload lúc chưa có key, sau khi set key hãy gọi: `POST /api/rag/rebuild` để index lại

Bạn có thể kiểm tra trạng thái tại: `GET /api/health` → field `vector`

### 6.0b Corrective RAG (CRAG) — chống truy hồi sai / câu hỏi “rác”

Project đã thêm **Corrective RAG**: retrieve → chấm mức liên quan → (nếu yếu) tự rewrite query → retrieve lại.

- Endpoint demo: `POST /api/rag/corrective_search`
- Được dùng nội bộ trong: `/api/quiz/generate` và `/api/assessments/generate` (giảm trộn chủ đề + bám sát tài liệu hơn)

### 6.0c Virtual AI Tutor (Student)

- UI: menu **🤖 Tutor** (student)
- API: `POST /api/tutor/chat`

Tutor chỉ trả lời dựa trên chunk evidence; nếu OCR lỗi sẽ trả `NEED_CLEAN_TEXT`.


### 6.1 Upload tài liệu → RAG search

1) `POST /api/documents/upload` (multipart form)
- `file`: chọn file .pdf/.docx/.pptx/.txt
- `user_id` (optional, default 1)
- `title` (optional)
- `tags` (optional, ví dụ: `sql,postgres`)

2) `POST /api/rag/search`
```json
{ "query": "<câu hỏi>", "top_k": 5, "filters": {"document_ids": [1]} }
```

### 6.2 Generate quiz → Submit → Score

1) `POST /api/quiz/generate`
```json
{
  "user_id": 1,
  "topic": "PostgreSQL",
  "level": "beginner",
  "question_count": 5,
  "rag": {"query": "PostgreSQL indexing", "top_k": 6, "filters": {"document_ids": [1]}}
}
```

2) `POST /api/quiz/{quiz_id}/submit`
```json
{
  "user_id": 1,
  "duration_sec": 120,
  "answers": [{"question_id": 1, "answer": 0}]
}
```

### 6.3 Exam templates → Generate → Analyze → Export (NEW)

1) `GET /api/exams/templates`

2) `POST /api/exams/generate-from-template`
```json
{
  "template_id": "pretest_standard",
  "user_id": 1,
  "level": "beginner",
  "document_ids": [1],
  "topics": ["PostgreSQL"],
  "title": "Bài test đầu vào - PostgreSQL"
}
```

3) `GET /api/exams/{assessment_id}/analyze`

4) `GET /api/exams/{assessment_id}/export?format=pdf` (hoặc `docx`)

Postman collection mẫu: `docs/week2_postman_collection.json`

### 6.3 Diagnostic (phân level) → Profile → Gợi ý bài tiếp theo (Week3)

1) `GET /api/profile/diagnostic/questions` (lấy bộ câu hỏi đầu vào)

2) `POST /api/profile/diagnostic` (nộp bài diagnostic → trả level)
```json
{
  "user_id": 1,
  "answers": [
    {"question_id": 1, "answer": 0},
    {"question_id": 2, "answer": 0}
  ]
}
```

3) `GET /api/profile/{user_id}` (xem level + mastery)

4) `GET /api/profile/{user_id}/next?topic=postgresql` (gợi ý level tiếp theo theo mastery(topic))

> Lưu ý: Khi submit quiz (`/api/quiz/{id}/submit`), backend sẽ tự cập nhật `mastery_json[topic]` theo rule đơn giản: đúng +α, sai -β (clamp 0..1).


### 6.4 Final test (post-test) → So sánh với đầu vào

Sau khi học viên ôn tập (làm nhiều quiz practice), chạy post-test để đo tiến bộ.

1) `POST /api/profile/final` (payload giống /profile/diagnostic)
```json
{
  "user_id": 1,
  "answers": [
    {"question_id": 1, "answer": 0},
    {"question_id": 2, "answer": 0}
  ]
}
```

Response có thêm:
- `pre_score_percent`: điểm đầu vào (lần pre gần nhất)
- `delta_score`: chênh lệch điểm

2) `GET /api/evaluation/{user_id}/overall` (lấy tổng quan tiến bộ)


## 3) (Tuỳ chọn) Chạy Flowise để orchestration AI Agents

Flowise giúp bạn dựng AgentFlow (multi-agent) và gọi API backend như các tool.

- File: `flowise/docker/docker-compose.flowise.yml`
- Tài liệu: `flowise/blueprints/agentflow_v2_orchestrator_blueprint.md`

Chạy (nếu bạn đang dùng docker compose của project):

```bash
# tạo network nội bộ nếu chưa có (docker-compose.yml của project tạo sẵn khi up)
# docker compose up -d  (ở root project)

# chạy Flowise (join cùng network internal)
docker compose -f flowise/docker/docker-compose.flowise.yml up -d
```

Mở Flowise: http://localhost:3000
