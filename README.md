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

### 5.4 Lỗi `pytest` / `pytest-cov` ở backend

Khi CI hoặc local báo lỗi liên quan `pytest`/`pytest-cov`, chạy lần lượt:

```bash
cd backend
pip show pytest pytest-cov
pip install pytest-cov
pytest --cov=app --cov-report=term-missing --cov-fail-under=70 -q
```

Nếu vẫn lỗi, kiểm tra lại `backend/pytest.ini` để chắc rằng các tham số coverage không bị cấu hình sai.

### 5.5 Lỗi `npm ci` / lệch `package-lock.json` ở frontend

Khi `npm ci` fail do lockfile không đồng bộ:

```bash
cd frontend
npm install
npm ci
```

### 5.6 Backend/Worker crash với lỗi `set: pipefail: invalid option name`

Triệu chứng thường gặp trên Windows:

- `backend-1 exited with code 2`
- `worker-1 exited with code 2`
- log chứa `set: pipefail: invalid option name`

Nguyên nhân: script shell trong `backend/` bị checkout thành CRLF (`\r\n`), trong khi container Linux cần LF (`\n`). Repo đã thêm `.gitattributes` để giữ LF cho `*.sh` và `*.py`, nhưng nếu bạn đã clone trước đó thì cần normalize lại file local:

```bash
git add --renormalize .
git commit -m "chore: normalize line endings" # nếu có thay đổi
docker compose down -v
docker compose up --build
```

Nếu không muốn commit local, có thể chạy nhanh:

```bash
git reset --hard
docker compose down -v
docker compose up --build
```

Nếu còn thiếu package, cài lại nhóm phụ thuộc đang bị thiếu rồi chạy lại `npm ci`:

```bash
npm install recharts@2.15.4 clsx@2.1.1 eventemitter3@4.0.7 lodash@4.17.23 react-is@18.3.1 react-smooth@4.0.4 recharts-scale@0.4.5 tiny-invariant@1.3.3 victory-vendor@36.9.2 fast-equals@5.4.0 prop-types@15.8.1 react-transition-group@4.4.5 loose-envify@1.4.0 object-assign@4.1.1 @babel/runtime@7.28.6 dom-helpers@5.2.1 decimal.js-light@2.5.1 @types/d3-array@3.2.2 @types/d3-ease@3.0.2 @types/d3-interpolate@3.0.4 @types/d3-scale@4.0.9 @types/d3-shape@3.1.8 @types/d3-time@3.0.4 @types/d3-timer@3.0.2 d3-array@3.2.4 d3-ease@3.0.1 d3-interpolate@3.0.1 d3-scale@4.0.2 d3-shape@3.2.0 d3-time@3.1.0 d3-timer@3.0.1 @types/d3-color@3.1.3 @types/d3-path@3.1.1 internmap@2.0.3 d3-color@3.1.0 d3-format@3.1.2 d3-time-format@4.1.0 d3-path@3.1.0
npm ci
```

### 5.7 Lỗi `TLS handshake timeout` khi pull base image Python

Nếu bạn gặp lỗi tương tự:

- `failed to resolve source metadata for docker.io/library/python:3.12-slim-bookworm`
- `net/http: TLS handshake timeout`

Nguyên nhân thường là mạng tới Docker Hub không ổn định (đặc biệt ở một số mạng công ty/VPN).

Repo đã đổi mặc định base image backend/worker sang mirror `public.ecr.aws` để giảm lỗi này.

Bạn có thể chạy lại:

```bash
docker compose down -v
docker compose up --build
```

Nếu muốn ép lại Docker Hub (khi mạng ổn định), override build arg:

```bash
PYTHON_BASE_IMAGE=python:3.12-slim-bookworm docker compose build --no-cache backend worker
docker compose up --build
```


### 4.4 Auth router gate (`AUTH_ENABLED`)

- `AUTH_ENABLED=true`: mount đầy đủ các endpoint `/api/auth/*` (ví dụ `/api/auth/login`, `/api/auth/register`).
- `AUTH_ENABLED=false` (mặc định): **không mount** auth router, client gọi `/api/auth/*` sẽ nhận `404 Not Found`.

Điều này cho phép chạy demo header mode mà không expose luồng JWT/email-password khi chưa cần.

## 5) Chạy dev local (không dùng container backend/frontend)
### 5.1 Chạy Backend

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

## Auth + phân quyền (Admin/Teacher/Student)

### Backend env tối thiểu
- Sao chép `backend/.env.example` -> `backend/.env`.
- Cấu hình bắt buộc:
  - `AUTH_ENABLED=true` để dùng JWT.
  - `ADMIN_EMAIL`, `ADMIN_PASSWORD` để seed tài khoản admin mặc định khi startup.
  - `DEMO_SEED=true` chỉ dùng khi `ENV=dev` để tạo dữ liệu demo.

### Luồng tài khoản
- `/api/auth/register`: chỉ đăng ký **student** và bắt buộc `student_code` (MSSV).
- Admin quản lý user qua:
  - `POST /api/admin/users/teachers`
  - `POST /api/admin/users/students`
  - `GET /api/admin/users`
  - `PATCH /api/admin/users/{id}`

### Frontend env
- Sao chép `frontend/.env.example` -> `frontend/.env`.
- `VITE_DEMO_MODE=true` mới bật 2 nút demo đăng nhập (Demo GV cấp sẵn + Demo SV).
- Mặc định `VITE_DEMO_MODE=false` dùng form email/password + đăng ký SV có MSSV.

## Production redesign artifacts

- Blueprint theo 10 phase: `docs/production_upgrade_blueprint.md`
- OpenAPI v3 spec draft: `backend/openapi/adaptive_learning_openapi_v1.yaml`
- Adaptive scoring engine (typed service): `backend/app/services/adaptive_engine.py`
- Unit tests for adaptive logic: `backend/tests/services/test_adaptive_engine.py`

## Enterprise Multi-Agent Refactor (vNext)

Bản refactor kiến trúc enterprise đã được scaffold trong thư mục `app/` theo Clean Architecture + Ports & Adapters.

- Tài liệu thiết kế: `docs/enterprise_multi_agent_architecture.md`
- Điểm vào demo: `python -m app.interfaces.cli.main`
- Test deterministic cho orchestration/guardrails: `pytest tests/unit -q`
