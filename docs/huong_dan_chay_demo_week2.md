# Hướng dẫn chạy & demo Week 2 (Windows PowerShell)

## 1) Nếu gặp lỗi Alembic `DEFAULT "mcq"`
Lỗi thường gặp khi migrate (PostgreSQL):

```
psycopg.errors.FeatureNotSupported: cannot use column reference in DEFAULT expression
LINE 6:  type VARCHAR(50) DEFAULT "mcq" NOT NULL,
```

Nguyên nhân: PostgreSQL coi **"mcq"** là *identifier* (tên cột) vì dùng **double quotes**.
Cách đúng: dùng string literal **'mcq'**.

Trong repo này, file migration đã được fix:
- `backend/alembic/versions/2f3b7c2f0b0a_week2_schema.py`
- Dòng cột `type` của bảng `questions` được đổi từ `"mcq"` → `'mcq'`.

---

## 2) Chạy lại sạch DB (khuyến nghị khi vừa migrate lỗi)
Trong thư mục project:

```powershell
docker compose down -v
 docker compose up --build
```

---

## 3) Test API trên PowerShell (dùng `curl.exe`)
PowerShell thường alias `curl` thành `Invoke-WebRequest`, nên hãy dùng **`curl.exe`**.

### 3.1 Upload tài liệu
```powershell
curl.exe -X POST "http://localhost:8000/api/documents/upload" `
  -F "file=@sample.pdf" `
  -F "user_id=1" `
  -F "title=Tai lieu demo" `
  -F "tags=sql,postgres"
```

### 3.2 RAG search
```powershell
curl.exe -X POST "http://localhost:8000/api/rag/search" `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"RAG la gi?\",\"top_k\":5,\"filters\":{}}"
```

### 3.3 Generate quiz
```powershell
curl.exe -X POST "http://localhost:8000/api/quiz/generate" `
  -H "Content-Type: application/json" `
  -d "{\"user_id\":1,\"topic\":\"RAG\",\"level\":\"beginner\",\"question_count\":5,\"rag\":{\"query\":\"RAG la gi?\",\"top_k\":6,\"filters\":{}}}"
```

### 3.4 Submit quiz
```powershell
curl.exe -X POST "http://localhost:8000/api/quiz/1/submit" `
  -H "Content-Type: application/json" `
  -d "{\"user_id\":1,\"duration_sec\":120,\"answers\":[{\"question_id\":1,\"answer\":0}]}"
```

---

## 4) Swagger
- Backend: `http://localhost:8000/docs`
- Frontend: `http://localhost:5173/`
