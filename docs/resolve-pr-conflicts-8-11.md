# Hướng dẫn xử lý conflict cho PR #8 và PR #11

Tài liệu này giúp xử lý đúng các conflict đang xuất hiện trong ảnh chụp GitHub:

- PR #11 conflict ở:
  - `backend/app/api/routes/lms.py`
  - `backend/app/services/lms_service.py`
- PR #8 conflict ở:
  - `backend/app/services/topic_service.py`
  - `backend/app/services/vietnamese_font_fix.py`

## Nguyên nhân chính

Hai nhánh được tạo từ commit cũ, trong khi `main` đã thay đổi các file cốt lõi ở API route và service.
Khi merge/rebase, Git không thể tự động quyết định giữ phần nào.

## Cách xử lý khuyến nghị (an toàn nhất)

> Ưu tiên **rebase lên `main` mới nhất**, resolve conflict tại local, chạy test rồi push lại nhánh.

## Quy trình cho PR #11

```bash
git fetch origin
git checkout codex/upgrade-ai-learning-agent-with-reporting-features
git rebase origin/main
```

Khi dừng ở conflict:

```bash
# Mở file và giữ cả 2 phía nếu đều cần
code backend/app/api/routes/lms.py
code backend/app/services/lms_service.py

# Sau khi sửa xong
git add backend/app/api/routes/lms.py backend/app/services/lms_service.py
git rebase --continue
```

Lặp lại đến khi rebase xong, sau đó chạy test backend:

```bash
pytest -q backend/tests/test_lms_service.py backend/tests/test_auto_routing.py
```

Cuối cùng push cập nhật nhánh PR:

```bash
git push --force-with-lease origin codex/upgrade-ai-learning-agent-with-reporting-features
```

## Quy trình cho PR #8

```bash
git fetch origin
git checkout codex/improve-topic_service.py-for-font-issues
git rebase origin/main
```

Khi dừng ở conflict:

```bash
code backend/app/services/topic_service.py
code backend/app/services/vietnamese_font_fix.py

git add backend/app/services/topic_service.py backend/app/services/vietnamese_font_fix.py
git rebase --continue
```

Chạy test liên quan font/topic:

```bash
pytest -q backend/tests/test_vietnamese_font_fix.py backend/tests/test_pdf_pipeline.py
```

Push lại nhánh:

```bash
git push --force-with-lease origin codex/improve-topic_service.py-for-font-issues
```

## Checklist resolve conflict đúng

- Không còn marker `<<<<<<<`, `=======`, `>>>>>>>` trong file.
- Endpoint LMS vẫn trả đúng schema API route.
- Logic phân loại/learning path trong `lms_service.py` không bị mất.
- Logic sửa font tiếng Việt trong `vietnamese_font_fix.py` vẫn giữ đầy đủ map + fallback.
- Tất cả test chính liên quan đều pass.

## Mẹo giảm conflict cho các PR sau

- Rebase nhánh feature lên `origin/main` mỗi ngày (hoặc trước khi mở PR).
- Với file “nóng” (route/service), tách helper mới sang file riêng thay vì sửa cùng block lớn.
- Mỗi PR chỉ nên tập trung một nhóm chức năng, tránh gom quá nhiều concern vào cùng file.
