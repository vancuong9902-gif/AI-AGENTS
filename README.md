# AI Learning Agent (Project Skeleton)

Khung project cho đề tài _Cá nhân hoá chương trình học dựa trên AI Agent_.

- **Backend**: FastAPI + SQLAlchemy + Alembic
- **DB**: Postgres + Redis (Docker Compose)
- **Frontend**: React + Vite

## 1) Prerequisites

- Docker Engine + Docker Compose plugin (`docker compose version`)
- Git
- Port trống: `5432` (Postgres), `6379` (Redis), `8000` (Backend), `5173` (Frontend)

## 2) Env audit (đã chuẩn hoá)

| Nguồn env | Mục đích | Trạng thái |
|---|---|---|
| `root/.env` | Optional cho biến shell/local override khi chạy tay | Không bắt buộc, có thể không tồn tại |
| `root/.env.example` | Template chính cho onboarding | ✅ Dùng để copy sang `backend/.env` |
| `backend/.env.example` | Template mirror cho chạy backend local | ✅ Đồng bộ nội dung với `root/.env.example` |
| `backend/.env` | File runtime được `docker-compose.yml` load | ✅ Bắt buộc khi chạy Compose |
| `docker-compose.yml` | Có `env_file: ./backend/.env` + env inline cho từng service | ✅ Không cần sửa đường dẫn khác |

> Kết luận: onboarding thống nhất theo 1 luồng: **copy `root/.env.example` -> `backend/.env`** rồi chạy `docker compose up`.

## 3) Quickstart (clone là chạy) 

Chạy tại thư mục root:

```bash
git clone <repo-url>
cd AI-AGENTS
cp .env.example backend/.env
docker compose up --build -d
docker compose ps
```

Mở:
- Frontend: http://localhost:5173
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

## 4) Migration / seed

Sau khi stack lên, chạy migration để đảm bảo schema mới nhất:

```bash
docker compose exec backend alembic upgrade head
```

Hiện tại project **không có seed script riêng**. Dữ liệu mẫu được tạo qua API/UI.

## 5) Troubleshooting

### 5.1 Lỗi DB migrate / thiếu bảng

```bash
docker compose exec backend alembic upgrade head
docker compose restart backend worker
```

### 5.2 Worker/Redis không xử lý job

```bash
docker compose logs --tail=200 redis
docker compose logs --tail=200 worker
docker compose up --build -d worker
```

### 5.3 Lỗi CORS khi frontend gọi backend

- Mặc định Compose đã set:
  - `BACKEND_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]`
- Nếu frontend chạy port/domain khác: sửa `BACKEND_CORS_ORIGINS` trong `docker-compose.yml`, rồi rebuild backend:
  - `FRONTEND_ORIGIN=http://localhost:5173`
  - `BACKEND_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]` (fallback khi chưa set FRONTEND_ORIGIN)
- Production: luôn set `FRONTEND_ORIGIN` cụ thể, không dùng wildcard `*`.
- Nếu bạn chạy frontend ở port/domain khác, cập nhật `FRONTEND_ORIGIN` (hoặc `BACKEND_CORS_ORIGINS`) trong `docker-compose.yml`, rồi restart backend:

```bash
docker compose up -d --build backend
```

## 6) Chạy local không dùng Docker (tuỳ chọn)

### Backend

```bash
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
Mở Swagger:

- http://localhost:8000/docs

Health check:

- http://localhost:8000/health
- http://localhost:8000/api/health

### 5.2 Chạy Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## 7) Tài liệu liên quan

- `docs/CONTRIBUTING.md`
- `docs/reports/weekly_template.md`
- `.github/pull_request_template.md`
