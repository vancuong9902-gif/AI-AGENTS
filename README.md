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

## 2) Prerequisites

- Docker Engine + Docker Compose plugin (`docker compose version`)
- (Khuyến nghị) Git, Bash/Zsh
- Port trống: `5432` (Postgres), `6379` (Redis), `8000` (Backend), `5173` (Frontend)

## 3) Quickstart (clone là chạy)

Tại thư mục root:

```bash
cp .env.example backend/.env
docker compose up --build -d
docker compose ps
docker compose logs -f backend
```

Mở:

- Frontend: http://localhost:5173
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

> Lưu ý về env:
> - `docker-compose.yml` đang load biến app từ `backend/.env` (`env_file: ./backend/.env`).
> - Vì vậy quickstart copy từ **root/.env.example** sang **backend/.env** để chạy đúng ngay sau khi clone.

## 4) Troubleshooting

### 4.1 DB migrate chưa chạy / lỗi thiếu bảng

```bash
docker compose exec backend alembic upgrade head
```

Nếu backend đã chạy lâu và đổi schema, có thể restart lại backend/worker:

```bash
docker compose restart backend worker
```

### 4.2 Redis/worker không xử lý job

Kiểm tra trạng thái:

```bash
docker compose ps
docker compose logs --tail=200 redis
docker compose logs --tail=200 worker
```

Nếu worker die do env cũ, copy lại env rồi dựng lại:

```bash
cp .env.example backend/.env
docker compose up --build -d worker
```

### 4.3 CORS khi frontend gọi backend

- Mặc định Compose đã set:
  - `BACKEND_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]`
- Nếu bạn chạy frontend ở port/domain khác, thêm origin mới vào biến `BACKEND_CORS_ORIGINS` trong `docker-compose.yml`, rồi restart backend:

```bash
docker compose up -d --build backend
```

## 5) Chạy dev local (không dùng container backend/frontend)
### 5.1 Chạy Backend



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

### 5.2 Chạy Frontend

```bash
cd ../frontend
cp .env.example .env
npm install
npm run dev
```

Mở web:

- http://localhost:5173

## 6) Chạy local (không dùng Docker)

- Cài Postgres local và tạo DB `ai_agent`
- Sửa `DATABASE_URL` trong `backend/.env` cho đúng máy bạn

## 7) Quy ước làm việc nhóm

Xem:

- `docs/CONTRIBUTING.md`
- `docs/reports/weekly_template.md`
- `.github/pull_request_template.md`

## 8) Luồng demo tuần 2 (Postman/Swagger)
### 6.0 Semantic RAG (FAISS) — ghép nối từ Week1

Mặc định, RAG sẽ **fallback keyword** (chạy được ngay, không cần thêm deps).

Nếu bạn muốn **semantic search giống Week1** (FAISS + OpenAI embeddings):
- **Docker Compose:** deps semantic đã được cài sẵn trong image backend. Chỉ cần set `OPENAI_API_KEY` trong `backend/.env` (có thể copy từ `root/.env.example`) rồi `docker compose up --build`.
- **Chạy local (venv):** cài thêm deps: `pip install -r backend/requirements.semantic.txt`.
- Set `OPENAI_API_KEY` trong `backend/.env` (khi chạy uvicorn từ thư mục `backend`).
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


## 7) LMS End-to-End API nhanh (Placement/Final + Classification)

Sau khi chạy backend, dùng thêm các endpoint LMS mới:

- `POST /api/lms/teacher/select-topics`
- `POST /api/lms/placement/generate`
- `POST /api/lms/final/generate`
- `POST /api/lms/attempts/{assessment_id}/submit`
- `GET /api/lms/teacher/report/{classroom_id}`

Xem bản audit + mapping requirement đầy đủ tại `docs/lms_audit_upgrade.md`.
