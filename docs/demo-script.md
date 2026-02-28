# Demo script end-to-end (teacher/student)

1. Start services:
   - `docker compose up --build`
2. Teacher upload tài liệu:
   - Login role teacher.
   - Vào `/upload`, upload PDF có tiếng Việt.
   - Kiểm tra `pdf_report.extractor_chosen`, `selection_reason`, topics.
3. Teacher tạo placement/final:
   - Dùng API `POST /api/quizzes/placement` (hoặc final) với `topic_ids`, `difficulty_settings`, `duration_seconds`.
4. Student làm bài:
   - `POST /api/attempts/start` để lấy `attempt_id`.
   - Submit bằng `POST /api/attempts/{id}/submit`.
   - Verify score + breakdown + classification + timed_out.
5. Recommendation + assignment:
   - `GET /api/students/{id}/recommendations`.
6. Teacher report:
   - `GET /api/teacher/reports?classroom_id=1`.
