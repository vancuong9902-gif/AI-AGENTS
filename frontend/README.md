# Frontend cơ bản (Vite + Vanilla JS)

Frontend đã được rút gọn để tập trung vào các chức năng cơ bản:

- Đăng nhập bằng email + password qua `POST /api/login`.
- Sau khi đăng nhập: hiển thị dữ liệu từ backend:
  - `GET /api/assessments` (cần token)
  - `GET /api/exams/templates` (công khai)
- Có các nút thao tác mẫu để tương tác API (`Làm bài kiểm tra`, `Tải tài liệu`).

## Chạy local

```bash
npm install
npm run dev
```

Mặc định frontend chạy tại `http://localhost:5173`.

## Cấu hình backend

Dùng proxy của Vite:

- Mặc định proxy đến `http://localhost:8000`
- Có thể đổi bằng biến môi trường `VITE_API_ORIGIN`

Ví dụ:

```bash
VITE_API_ORIGIN=http://localhost:8000 npm run dev
```

## Tài khoản demo

Nếu backend đã seed dữ liệu demo, bạn có thể dùng tài khoản tương ứng trong backend để đăng nhập.
