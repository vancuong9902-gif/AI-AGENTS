# AI-AGENTS LMS Audit & Upgrade Map

## 1) Sơ đồ luồng hiện tại (đã chuẩn hoá cho end-to-end)

`upload -> extract/pdf_report -> normalize tiếng Việt -> topic split -> teacher chọn topic -> generate placement/final -> student submit (timer) -> auto score + breakdown -> classify -> recommendation -> teacher report`

Các điểm chạm chính trong code:
- Upload + extract + `pdf_report`: `POST /api/documents/upload` và pipeline extractor đa chiến lược trong `document_pipeline.py`.
- Topic extraction + phân nhóm: route `documents.py` + `topic_service.py`.
- Tạo bài kiểm tra đầu vào/cuối kỳ: `POST /api/lms/placement/generate`, `POST /api/lms/final/generate` (wrapper trên assessment service).
- Student submit/chấm điểm/breakdown/classification/recommendation: `POST /api/lms/attempts/{assessment_id}/submit`.
- Dashboard báo cáo giáo viên theo lớp: `GET /api/lms/teacher/report/{classroom_id}`.

## 2) Requirement -> Hiện trạng -> Thiếu -> Fix

| Requirement | Hiện trạng | Thiếu | Fix đã làm |
|---|---|---|---|
| Upload PDF + extract đủ + giải thích extractor | Đã có multi-extractor và scoring completeness | Router exams chưa mount, flow LMS rời rạc | Bổ sung router LMS hợp nhất và mount router exams/lms vào app |
| Normalize tiếng Việt | Có normalize trong pipeline | Chưa có test normalize rõ ràng | Thêm test normalize + page coverage |
| Teacher chọn topic tạo placement (3 difficulty + timer) | Assessment có timer và auto-submit FE | Chưa có API “LMS” rõ placement/final | Thêm `/api/lms/placement/generate`, `/api/lms/final/generate`, `/api/lms/teacher/select-topics` |
| Student submit chấm điểm ngay + breakdown | Có submit assessment | Chưa có breakdown theo độ khó/topic + phân loại | Thêm `lms_service.score_breakdown`, classify, recommendation trong endpoint submit |
| Cá nhân hoá học liệu/bài tập | Có learning plan/adaptive rời rạc | Chưa nối trực tiếp sau submit | Endpoint submit trả `recommendations` theo topic yếu |
| Teacher report cuối kỳ | Có analytics rời rạc | Chưa có endpoint report gọn cho luồng LMS | Thêm `GET /api/lms/teacher/report/{classroom_id}` |

## 3) API tối thiểu cho demo E2E

- `POST /api/documents/upload`
- `GET /api/documents/{document_id}/topics?detail=1`
- `POST /api/lms/teacher/select-topics`
- `POST /api/lms/placement/generate`
- `POST /api/lms/attempts/{assessment_id}/submit`
- `POST /api/lms/final/generate`
- `GET /api/lms/teacher/report/{classroom_id}`

## 4) Demo script ngắn

1. Teacher upload PDF, lấy `document_id`.
2. Gọi topics detail, chọn 3-5 topic trọng tâm.
3. Gọi `select-topics`.
4. Sinh placement test (`/lms/placement/generate`), mở FE làm bài với timer.
5. Submit qua `/lms/attempts/{id}/submit` nhận `score_breakdown`, `student_level`, `recommendations`.
6. Sinh final test (`/lms/final/generate`) với topics tương tự hoặc mở rộng.
7. Xem báo cáo lớp qua `/lms/teacher/report/{classroom_id}`.
