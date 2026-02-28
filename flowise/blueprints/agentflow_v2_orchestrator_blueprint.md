# Flowise AgentFlow V2 — Blueprint cho AI Learning Agents

Tài liệu này giúp bạn dựng nhanh **AI Agents cho học tập** trong Flowise để bám đúng sơ đồ swimlane (Giảng viên ↔ AI Agent System ↔ Sinh viên).

## 0) Yêu cầu
- Backend (project này) chạy tại: `http://localhost:8000`
- Flowise chạy tại: `http://localhost:3000`
- Frontend demo chạy tại: `http://localhost:5173`

> Nếu bạn dùng Docker Compose của project:
> - DB/Backend/Frontend dùng network `internal`
> - File `flowise/docker/docker-compose.flowise.yml` chạy Flowise và join vào network `internal`

## 1) Mục tiêu Flowise trong project
Flowise đóng vai trò **orchestrator**:
- Nhận yêu cầu (Teacher/Student action)
- Gọi API backend (Tools/HTTP request)
- Chuẩn hoá output JSON (structured output) để frontend hiển thị

## 2) Các Tool (HTTP) cần tạo trong Flowise
Tạo các **Custom Tool** (HTTP) trỏ đến backend:

### (T1) Lấy danh sách tài liệu
- `GET http://backend:8000/api/documents`

### (T2) Lấy topics của tài liệu
- `GET http://backend:8000/api/documents/{document_id}/topics`

### (T3) Sinh quiz theo topic/level
- `POST http://backend:8000/api/quiz/generate`
Body JSON (ví dụ):
```json
{
  "user_id": 2,
  "topic": "Biến và kiểu dữ liệu",
  "level": "beginner",
  "question_count": 10,
  "rag": {
    "query": "Biến và kiểu dữ liệu",
    "top_k": 6,
    "filters": {"document_ids": [1]}
  }
}
```

### (T4) Chấm quiz
- `POST http://backend:8000/api/quiz/{quiz_id}/submit`

### (T5) Tutor chat
- `POST http://backend:8000/api/tutor/chat`

### (T6) Generate practice questions (không dùng framework cố định)
- `POST http://backend:8000/api/tutor/generate-questions`

### (T7) Generate Question Bank cho toàn bộ topics (Teacher)
> Endpoint này được thêm trong bản zip v2:  
- `POST http://backend:8000/api/documents/{document_id}/question-bank/generate`

## 3) AgentFlow V2: Orchestrator (1 flow duy nhất)
Tạo 1 AgentFlow V2 tên: **AILA Orchestrator**

### Start Form fields đề xuất
- `action` (select):
  - `generate_pretest`
  - `generate_question_bank`
  - `tutor_chat`
  - `submit_quiz`
- `user_id` (number)
- `document_id` (number, optional)
- `topic` (string, optional)
- `level` (select: beginner/intermediate/advanced)
- `question_count` (number, default 10)
- `question` (string, tutor chat)

### Routing logic (Condition/Switch)
- action == `generate_pretest` → gọi T3 (quiz/generate) với `question_count`, `topic`, `level`, `document_ids`
- action == `generate_question_bank` → gọi T7
- action == `tutor_chat` → gọi T5
- action == `submit_quiz` → gọi T4

### Output chuẩn
Trả về JSON gồm:
- `action`
- `status`
- `data` (payload từ backend)
- `error` (nếu có)

## 4) Ví dụ gọi Flowise Prediction API từ app
Flowise Prediction API (AgentFlow V2 thường dùng `form`) — ví dụ curl:

```bash
curl -X POST "http://localhost:3000/api/v1/prediction/<FLOW_ID>" \
  -H "Content-Type: application/json" \
  -d '{
    "form": {
      "action": "generate_pretest",
      "user_id": 2,
      "document_id": 1,
      "topic": "Biến và kiểu dữ liệu",
      "level": "beginner",
      "question_count": 10
    }
  }'
```

## 5) Checklist để demo theo sơ đồ swimlane
- Teacher upload tài liệu (frontend/backend)
- Teacher gọi Flowise action: `generate_question_bank`
- Student gọi Flowise action: `generate_pretest`
- Student submit quiz (frontend hoặc Flowise action: `submit_quiz`)
- Student chat tutor: `tutor_chat`
- Teacher xem báo cáo (backend endpoints sẵn có)

