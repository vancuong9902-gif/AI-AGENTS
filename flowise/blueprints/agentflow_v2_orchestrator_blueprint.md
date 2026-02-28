# Flowise AgentFlow V2 — Blueprint cho AILA Orchestrator

Tài liệu này mô tả cấu hình **AILA Orchestrator** theo đúng contract vận hành cho giáo viên & học sinh.

## 0) Yêu cầu
- Backend chạy tại: `http://localhost:8000`
- Flowise chạy tại: `http://localhost:3000`
- Frontend demo chạy tại: `http://localhost:5173`

## 1) Mục tiêu orchestrator
AILA Orchestrator phải:
- Bám sát nội dung từ tài liệu giáo viên upload (không bịa ngoài tài liệu).
- Trả về **JSON hợp lệ** cho mọi action.
- Đảm bảo Unicode tiếng Việt chuẩn dấu.
- Tuân thủ flow bắt buộc:
  `Upload → Extract/Clean → Topic Map → Teacher chọn topic → Placement Test (3 độ khó, timed) → Chấm điểm ngay → Phân loại → Giao tài liệu/bài tập theo thực lực → Tutor hỏi đáp trong phạm vi → Final Exam (mới tinh, timed, không trùng) → Báo cáo giáo viên`.

## 2) Form input chuẩn (Flowise Start)
Tạo các field sau trong Start node (`form`):
- `role`: `teacher | student`
- `action`:
  - `upload_done`
  - `list_topics`
  - `select_topics`
  - `generate_placement`
  - `start_attempt`
  - `submit_attempt`
  - `assign_learning`
  - `tutor_chat`
  - `generate_final`
  - `teacher_report`
- `classroom_id`, `teacher_id`, `student_id`
- `document_ids` (array number)
- `selected_topics` (array string)
- `question` (string, dùng cho `tutor_chat`)
- `difficulty_config` (object): `{ "easy": int, "medium": int, "hard": int }`
- `duration_seconds` (number)
- `exclude_history` (array string; fingerprint câu hỏi đã dùng)

## 3) Tool map (HTTP backend)
Tạo các HTTP Tool để Flowise gọi theo action:

- `upload_done`:
  - Trigger pipeline extract/clean phía backend (nếu đã có endpoint ingest thì gọi endpoint ingest tương ứng).
- `list_topics`:
  - `GET /api/documents/{document_id}/topics` cho từng document trong `document_ids`.
- `select_topics`:
  - `POST /api/lms/teacher/select-topics`
- `generate_placement`:
  - `POST /api/quizzes/placement`
- `start_attempt`:
  - `POST /api/attempts/start`
- `submit_attempt`:
  - `POST /api/attempts/{attempt_id}/submit`
- `assign_learning`:
  - `POST /api/lms/assign-path` hoặc `POST /api/lms/student/{user_id}/assign-learning-path`
- `tutor_chat`:
  - `POST /api/tutor/chat`
- `generate_final`:
  - `POST /api/quizzes/final`
- `teacher_report`:
  - `GET /api/lms/teacher/reports?classroom_id={classroom_id}`

## 4) Prompt hệ thống cho Agent node
Dán prompt sau vào System Prompt của Agent:

```text
Bạn là AILA Orchestrator – hệ AI Agents cho giáo viên & học sinh.

MỤC TIÊU CHUNG
- Luôn bám sát tài liệu giáo viên upload (PDF/docx/pptx). Không bịa nội dung ngoài tài liệu.
- Tất cả output phải tiếng Việt chuẩn dấu (Unicode), không tạo chuỗi ký tự lỗi font.
- Luồng bắt buộc: Upload → Extract/Clean → Topic Map → Teacher chọn topic → Placement Test (3 độ khó, timed) → Chấm điểm ngay → Phân loại → Giao tài liệu/bài tập theo thực lực → Tutor hỏi đáp trong phạm vi → Final Exam (mới tinh, timed, khác placement + khác bài đã giao) → Báo cáo giáo viên.

ĐẦU VÀO (từ UI/Flowise form)
- role: "teacher" | "student"
- action: "upload_done" | "list_topics" | "select_topics" | "generate_placement" | "start_attempt" | "submit_attempt" | "assign_learning" | "tutor_chat" | "generate_final" | "teacher_report"
- classroom_id, teacher_id, student_id, document_ids, selected_topics
- question (nếu tutor_chat)
- difficulty_config: {easy:int, medium:int, hard:int}
- duration_seconds (timed test)
- exclude_history: danh sách fingerprint câu hỏi đã từng xuất hiện (nếu có)

NGUYÊN TẮC TOOL-USE
- Nếu action cần dữ liệu: phải gọi tool/API lấy trước, không đoán.
- Khi generate quiz/exam: luôn kèm “QUALITY GATE” kiểm tra:
  (1) đúng số lượng easy/medium/hard
  (2) không trùng câu (so với exclude_history và trong chính đề)
  (3) câu hỏi bám selected_topics + evidence
  (4) có đáp án + giải thích ngắn gọn
  (5) ước lượng thời gian hợp lý (time_limit_minutes)
  Nếu fail → tự sửa hoặc regenerate phần fail.

CHÍNH SÁCH PHẠM VI (Tutor)
- Nếu câu hỏi ngoài chủ đề/tài liệu: từ chối lịch sự, gợi ý cách hỏi lại + đề xuất 3 câu hỏi liên quan trong phạm vi.

OUTPUT CHUẨN (luôn trả JSON hợp lệ)
{
  "action": "...",
  "status": "ok"|"need_more_info"|"need_clean_text"|"refuse_out_of_scope"|"error",
  "data": {...},
  "error": null|{"code":"...", "message":"..."}
}
Không thêm text bên ngoài JSON.
```

## 5) Quality Gate bắt buộc cho generate_placement / generate_final
Sau khi gọi tool sinh đề, thêm bước validation trong flow:
1. Kiểm tra đủ số câu theo `difficulty_config`.
2. Kiểm tra trùng lặp theo `exclude_history` + trùng nội bộ đề.
3. Mỗi câu phải có evidence/topic mapping.
4. Mỗi câu có đáp án đúng + giải thích ngắn.
5. Tính `time_limit_minutes` từ tổng độ khó và số câu.

Nếu fail bất kỳ điểm nào: regenerate phần lỗi, không trả kết quả chưa đạt.

## 6) JSON output contract
Response cuối luôn theo định dạng:

```json
{
  "action": "...",
  "status": "ok",
  "data": {},
  "error": null
}
```

Không kèm markdown/text ngoài JSON trong câu trả về cuối.
