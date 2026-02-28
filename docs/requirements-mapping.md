# Requirements Mapping

| Requirement | Hiện trạng | Thiếu gì | Đề xuất fix | File liên quan |
|---|---|---|---|---|
| Upload -> extract -> topics có report | Đã có `/documents/upload`, có `pdf_report` candidates | Thiếu trường giải thích chọn extractor rõ ràng | Bổ sung `extractor_chosen`, `selection_reason`, `page_coverage` tổng quan | `backend/app/services/document_pipeline.py` |
| Normalize tiếng Việt sau extract | Đã có `_normalize_pipeline_text` | Cần test rõ lỗi spacing/encoding artifacts | Mở rộng test normalize + duy trì NFKC + OCR spacing repair | `backend/tests/test_lms_service.py` |
| Placement/final quiz 3 độ khó + timer | Có LMS generate diagnostic pre/post | Chưa đúng endpoint contract mới + chưa start/submit theo `attempt_id` | Thêm endpoints alias `/quizzes/placement`, `/quizzes/final`, `/attempts/start`, `/attempts/{id}/submit` | `backend/app/api/routes/lms.py` |
| Chấm điểm ngay + breakdown + classification | Đã có `score_breakdown`, `classify_student_level` | Chưa expose endpoint submit theo contract mới | Reuse logic ở endpoint submit mới | `backend/app/services/lms_service.py`, `backend/app/api/routes/lms.py` |
| Recommendations/assignments theo điểm yếu | Đã có `build_recommendations` | Chưa có API student recommendations chuẩn | Thêm `GET /students/{id}/recommendations` | `backend/app/api/routes/lms.py` |
| Teacher report tổng hợp | Đã có `/lms/teacher/report/{classroom_id}` | Chưa có alias contract | Thêm `/teacher/reports` với filter classroom_id | `backend/app/api/routes/lms.py` |
| UI foundation design system | Có token cơ bản rải ở `index.css` | Thiếu utility/components đồng bộ | Mở rộng `theme.css`: tokens + utilities + Banner/Modal/Tabs/Table/Pagination/Skeleton | `frontend/src/ui/*.jsx`, `frontend/src/ui/theme.css` |
| AppShell chuyên nghiệp, responsive | Đã có shell cơ bản | Thiếu sidebar collapse/mobile drawer/a11y focus ring | Nâng cấp AppShell + Navbar | `frontend/src/App.jsx`, `frontend/src/App.css`, `frontend/src/components/Navbar.jsx` |
| Upload/Library/Quiz màn hình đẹp, có states | Có page nhưng chưa đồng nhất UX states | Thiếu page header/breadcrumbs/loading-empty-error chuẩn | Refactor pages + reusable components | `frontend/src/pages/Upload.jsx`, `frontend/src/pages/FileLibrary.jsx`, `frontend/src/pages/Quiz.jsx` |
| Docs run/demo/changelog | Có nhiều docs rời rạc | Thiếu demo script chuẩn end-to-end + changelog tập trung | Thêm `docs/demo-script.md`, `docs/changelog.md` | `docs/demo-script.md`, `docs/changelog.md` |
