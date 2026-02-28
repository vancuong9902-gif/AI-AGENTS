# Week 2 – Chuẩn hoá API contract + DB schema (RAG / Quiz / Attempt / Profile)

Tài liệu này để cả team bám theo cùng một chuẩn request/response (BE/FE/Agents).

> Bối cảnh: hệ thống cá nhân hoá học tập theo mô hình multi-agent (Content/RAG, Assessment/Quiz, Profiling, Adaptive, Evaluation). fileciteturn0file0

---

## 1) Quy ước chung

### 1.1 Headers
- `X-Request-ID` (optional): FE/Postman gửi lên để trace. Nếu không có BE tự tạo.
- `Content-Type: application/json` cho JSON endpoints.
- Upload dùng `multipart/form-data`.

### 1.2 Response envelope (khuyến nghị)
Tất cả endpoint trả JSON có cấu trúc:
```json
{
  "request_id": "uuid",
  "data": { ... },
  "error": null
}
```
Nếu lỗi:
```json
{
  "request_id": "uuid",
  "data": null,
  "error": { "code": "VALIDATION_ERROR", "message": "..." }
}
```

### 1.3 Entities IDs
- Dùng `uuid` (Postgres `uuid`) cho: `users`, `documents`, `chunks`, `quiz_sets`, `questions`, `attempts`, `rag_queries`.

### 1.4 Level (Profiling)
- `<40%` → `beginner`
- `40–70%` → `intermediate`
- `>70%` → `advanced` fileciteturn0file0

---

## 2) API Contract

### 2.1 Upload tài liệu
**POST `/documents/upload`**

**Request (multipart/form-data)**
- `file`: PDF/DOCX/PPTX
- `title` (optional): string
- `tags` (optional): string (comma-separated)
- `course_id` (optional): string/uuid (nếu có)

**Response**
```json
{
  "request_id": "uuid",
  "data": {
    "document_id": "uuid",
    "title": "string",
    "filename": "string",
    "mime_type": "string",
    "chunk_count": 42
  },
  "error": null
}
```

**Notes**
- BE gọi pipeline extract+chunk+embed (agent Bảo) và lưu:
  - DB: documents, document_chunks (metadata + text)
  - Vector DB: embeddings + metadata chunk_id/document_id

---

### 2.2 RAG retrieve (search)
**POST `/rag/search`** (khuyến nghị dùng POST vì payload có filter)

**Request**
```json
{
  "query": "string",
  "top_k": 5,
  "filters": {
    "document_ids": ["uuid"],
    "tags": ["string"]
  }
}
```

**Response**
```json
{
  "request_id": "uuid",
  "data": {
    "query_id": "uuid",
    "query": "string",
    "top_k": 5,
    "chunks": [
      {
        "chunk_id": "uuid",
        "document_id": "uuid",
        "title": "string",
        "chunk_index": 12,
        "score": 0.82,
        "text": "snippet / chunk text",
        "meta": { "page": 3, "source": "file.pdf" }
      }
    ]
  },
  "error": null
}
```

---

### 2.3 Generate quiz theo level/topic
**POST `/quiz/generate`**

**Request**
```json
{
  "user_id": "uuid",
  "topic": "string",
  "level": "beginner|intermediate|advanced",
  "question_count": 5,
  "rag": { "query": "string", "top_k": 6, "filters": { "document_ids": ["uuid"] } }
}
```

**Response**
```json
{
  "request_id": "uuid",
  "data": {
    "quiz_id": "uuid",
    "topic": "string",
    "level": "intermediate",
    "questions": [
      {
        "question_id": "uuid",
        "type": "mcq",
        "stem": "string",
        "options": ["A...", "B...", "C...", "D..."]
      }
    ],
    "sources": [
      { "chunk_id": "uuid", "document_id": "uuid", "score": 0.81 }
    ]
  },
  "error": null
}
```

**Notes**
- Quiz generator (Đức) có thể gọi `/rag/search` để lấy context.
- Lưu DB: `quiz_sets` + `questions` (không trả correct_answer ra FE).

---

### 2.4 Submit quiz, chấm điểm + lưu attempts
**POST `/quiz/{quiz_id}/submit`**

**Request**
```json
{
  "user_id": "uuid",
  "duration_sec": 120,
  "answers": [
    { "question_id": "uuid", "answer": 1 }
  ]
}
```
- `answer` là index trong `options` (0-based hoặc 1-based) → phải thống nhất. Khuyến nghị **0-based**.

**Response**
```json
{
  "request_id": "uuid",
  "data": {
    "quiz_id": "uuid",
    "attempt_id": "uuid",
    "score_percent": 80,
    "correct_count": 4,
    "total": 5,
    "breakdown": [
      {
        "question_id": "uuid",
        "is_correct": true,
        "chosen": 1,
        "correct": 1,
        "explanation": "string",
        "sources": [
          { "chunk_id": "uuid", "document_id": "uuid", "score": 0.77 }
        ]
      }
    ]
  },
  "error": null
}
```

---

### 2.5 Diagnostic (nếu đã có tuần 1)
**POST `/profile/diagnostic`**

**Request**
```json
{ "user_id":"uuid", "answers":[{"id":"q1","answer":2}] }
```
**Response**
```json
{
  "request_id":"uuid",
  "data":{"score_percent":65,"correct_count":13,"total":20,"level":"intermediate"},
  "error":null
}
```

---

## 3) DB Schema (PostgreSQL) – đề xuất

### 3.1 users
- `id uuid pk`
- `email text unique null`
- `full_name text null`
- `created_at timestamptz default now()`

### 3.2 learner_profiles
- `user_id uuid pk fk users(id)`
- `level text` (beginner/intermediate/advanced)
- `mastery_json jsonb` (vd: {"topicA":0.6})
- `updated_at timestamptz default now()`

### 3.3 documents
- `id uuid pk`
- `title text`
- `filename text`
- `mime_type text`
- `tags text[]`
- `created_at timestamptz default now()`

### 3.4 document_chunks
- `id uuid pk`
- `document_id uuid fk documents(id)`
- `chunk_index int`
- `text text`
- `meta jsonb` (page, slide, headings...)
- `created_at timestamptz default now()`
- unique(document_id, chunk_index)

### 3.5 rag_queries (lưu lịch sử)
- `id uuid pk`
- `user_id uuid null fk users(id)`
- `query text`
- `top_k int`
- `filters jsonb`
- `result_chunk_ids uuid[]`
- `created_at timestamptz default now()`

### 3.6 quiz_sets
- `id uuid pk`
- `user_id uuid fk users(id)`
- `topic text`
- `level text`
- `source_query_id uuid null fk rag_queries(id)`
- `created_at timestamptz default now()`

### 3.7 questions
- `id uuid pk`
- `quiz_set_id uuid fk quiz_sets(id) on delete cascade`
- `type text` (mcq)
- `stem text`
- `options jsonb` (array)
- `correct_index int`
- `explanation text null`
- `sources jsonb` (array chunk refs)
- `order_no int`
- index(quiz_set_id, order_no)

### 3.8 attempts
- `id uuid pk`
- `quiz_set_id uuid fk quiz_sets(id) on delete cascade`
- `user_id uuid fk users(id)`
- `score_percent int`
- `answers_json jsonb` (list user answers)
- `breakdown_json jsonb` (per question)
- `duration_sec int`
- `created_at timestamptz default now()`

---

## 4) End-to-end demo (Postman/curl)
- Flow A: `POST /documents/upload` → `POST /rag/search`
- Flow B: `POST /quiz/generate` → `POST /quiz/{id}/submit` → xem DB có quiz_sets/questions/attempts

