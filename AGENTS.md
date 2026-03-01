# AGENTS Instructions

## Quy tắc chung
1) Làm theo từng milestone, mỗi milestone 1 commit.
2) Trước khi sửa: đọc nhanh cấu trúc repo + tìm file liên quan.
3) Sau khi sửa: chạy test/lint/build phù hợp và ghi lại lệnh đã chạy.
4) Output cuối: liệt kê file thay đổi + git diff + hướng dẫn test thủ công.

## Frontend rules
- Không thêm thư viện UI mới.
- Tận dụng component sẵn có.
- Tránh inline styles; dùng className/theme tokens.

## Backend rules
- Không leak stacktrace ra client khi production.
- List endpoints phải có pagination; list không trả full text dài.

## Definition of Done
- Fix các bug High: LearningPath unwrap + JSON Content-Type + FileLibrary “Xem topics”.
- Loại BOM trong .py và có cơ chế chặn tái diễn.
- README/.env.example đúng, người mới clone chạy được.
- Auth router được mount đúng cách.
- Có pagination + tests cho pagination.
- UI đồng nhất; có loading/error/empty state chuẩn.
- Thêm CI tối thiểu chạy lint/build/test.
