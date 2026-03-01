# AI Learning Agent LMS 10/10 Upgrade Plan

## 0) Phân tích hiện trạng & bug cần chặn ngay

### Bug final hiện tại (critical)
- `generate_final_exam()` đang lấy `pre_exam_ids` bằng điều kiện `QuizSet.user_id == user_id` + `QuizSet.kind == diagnostic_pre`.
- Trong schema hiện tại, `QuizSet.user_id` là **teacher/creator id**, không phải learner id.
- Hệ quả: exclude set cho final có thể rỗng/sai user, làm đề final trùng placement hoặc trùng đề đã giao.
- Đã fix theo hướng:
  - Exclude theo **Attempt.user_id** của learner (diagnostic_pre + entry_test).
  - Hợp nhất thêm quiz diagnostic_pre đã assign trong classroom.
  - Truyền `dedup_user_id/attempt_user_id` vào generator cho final flow (`diagnostic_post`) để dedup theo đúng learner.

---

## A) Kế hoạch triển khai 6 phase (ưu tiên final + timer)

## Phase 1 — Final anti-dup correctness (P0)
**Mục tiêu**: Final “mới tinh”, không đụng placement/quiz cũ của learner, khác góc tiếp cận.

### Việc làm
- Chuẩn hoá exclude source:
  - Placement đã assign lớp.
  - Quiz/practice đã assign trong classroom.
  - Attempt history của learner (diagnostic_pre, entry_test, diagnostic_post/final cũ).
- Bắt buộc route final gọi generator với `attempt_user_id`/`dedup_user_id`.
- Bật final-specific hint cho cả `kind=diagnostic_post` (không chỉ `final_exam`).
- Thêm `similarity_threshold` configurable (default 0.75).

### Definition of Done
- [ ] Final mới không lặp stem (exact/fuzzy) với exclude set.
- [ ] `excluded_from_count` phản ánh đúng quy mô exclude.
- [ ] Unit test pass: có placement + assigned quizzes -> final không trùng.

## Phase 2 — Server-side timer hardening (P0)
**Mục tiêu**: duration chỉ tính server, client không thể gian lận.

### Việc làm
- Mọi submit/heartbeat đọc `started_at` từ server session.
- Tính `elapsed_seconds = now - started_at` trên server.
- Ignore/override `client_duration` ở submit API.
- Chuẩn hoá trạng thái timeout: `timed_out`, `remaining_seconds`, `late_submission`.

### Definition of Done
- [ ] Không endpoint nào dùng duration từ client để chấm điểm.
- [ ] Unit test pass: gửi `duration_sec` giả -> hệ thống vẫn dùng server elapsed.
- [ ] Attempt log có `start_time`, `submit_time`, `time_spent_seconds` nhất quán.

## Phase 3 — Export teacher report PDF/XLSX (P1)
**Mục tiêu**: xuất báo cáo thật, số liệu khớp API hiện có.

### Việc làm
- API export hợp nhất `format=pdf|xlsx`.
- PDF có chart: pre/post progress, level distribution, weak topics, study hours.
- XLSX gồm sheets: Grades, Progress, Weak Topics, Attempts Raw.
- Fallback dữ liệu rỗng: “chưa có dữ liệu”.

### Definition of Done
- [ ] PDF/XLSX export được kể cả lớp ít dữ liệu.
- [ ] Số liệu khớp endpoint report JSON.
- [ ] Unicode tiếng Việt hiển thị đúng.

## Phase 4 — Multi-variant DOCX exam generator (P1)
**Mục tiêu**: sinh N mã đề in ấn được, khác nhau tối thiểu 60%.

### Việc làm
- POST generate batch variants với config N/X/tỉ lệ MCQ-essay/easy-medium-hard/shuffle.
- Anti-overlap giữa variants theo config min_unique_ratio.
- Anti-overlap với ngân hàng đề đã dùng trước đó (similarity).
- Export ZIP gồm `N *.docx` + optional `answer_key.docx`.

### Definition of Done
- [ ] ZIP tải được, mở docx không lỗi font.
- [ ] Mỗi mã đề đạt ngưỡng khác biệt.
- [ ] Có metadata batch để audit/trace.

## Phase 5 — Study Pack artifacts sau placement (P1)
**Mục tiêu**: giao học liệu cá nhân hoá có persisted artifact thật.

### Việc làm
- Tạo bảng `study_packs` lưu theo user/topic/plan.
- Prompt grounding bắt buộc evidence chunks; OCR quality gate.
- Nội dung chuẩn: summary, outline, key points, defs/formulas, ví dụ, bài tập 3 mức + đáp án/giải thích.
- API create/get cho FE render.

### Definition of Done
- [ ] Sau placement có Study Pack theo weak topics.
- [ ] Khi OCR kém trả `NEED_CLEAN_TEXT` + hướng dẫn.
- [ ] JSON schema stable, FE render trực tiếp.

## Phase 6 — Session study time analytics (P1)
**Mục tiêu**: thống kê giờ học chuẩn cho dashboard.

### Việc làm
- Event log `/sessions/start`, `/sessions/end` cho study/tutor/quiz.
- Tính `total_minutes`, `minutes_by_day`, `minutes_by_activity` từ DB events.
- Anti-cheat: clamp duration max/session; close dangling sessions bằng heartbeat timeout policy.

### Definition of Done
- [ ] Dashboard hiển thị đủ 3 metric thời gian.
- [ ] Session data không âm, không double-count.
- [ ] Có raw attempts/session export phục vụ đối soát.

---

## B) Thiết kế API chi tiết

## 1) Teacher report export
### `GET /lms/teacher/report/{classroom_id}/export?format=pdf|xlsx`

**Query params**
```json
{
  "format": "pdf",
  "include_raw": false,
  "tz": "Asia/Ho_Chi_Minh"
}
```

**200 (file stream)**
- `Content-Type`: `application/pdf` hoặc `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `Content-Disposition`: `attachment; filename="classroom_{id}_report.{ext}"`

**Error payload**
```json
{
  "request_id": "...",
  "error": {
    "code": "INVALID_FORMAT",
    "message": "format must be pdf or xlsx"
  }
}
```

## 2) Exam variants
### `POST /exams/generate-variants`

**Request**
```json
{
  "teacher_id": 12,
  "classroom_id": 34,
  "title": "Final Exam HK1",
  "topic_ids": [101, 102, 103],
  "document_ids": [8, 9],
  "variants": 5,
  "questions_per_variant": 40,
  "mix": {"mcq": 0.75, "essay": 0.25},
  "difficulty": {"easy": 0.2, "medium": 0.5, "hard": 0.3},
  "shuffle_questions": true,
  "shuffle_options": true,
  "min_unique_ratio_between_variants": 0.6,
  "similarity_threshold": 0.78,
  "exclude_sources": {
    "placement": true,
    "assigned_quizzes": true,
    "historical_attempts": true
  },
  "include_answer_key": true,
  "print_layout": {
    "line_spacing": 1.3,
    "show_page_number": true,
    "header_text": "Trường ... - Môn ..."
  }
}
```

**202**
```json
{
  "request_id": "...",
  "data": {
    "batch_id": "evb_01J...",
    "status": "processing",
    "estimated_seconds": 25
  },
  "error": null
}
```

### `GET /exams/variants/{batch_id}/download`

**200**: stream file zip.

**409 (not ready)**
```json
{
  "request_id": "...",
  "error": {
    "code": "BATCH_NOT_READY",
    "status": "processing",
    "progress": 62
  }
}
```

## 3) Session logging
### `POST /sessions/start`

**Request**
```json
{
  "user_id": 99,
  "classroom_id": 34,
  "activity": "tutor",
  "context": {
    "quiz_id": 501,
    "topic": "Hàm số bậc hai"
  }
}
```

**200**
```json
{
  "request_id": "...",
  "data": {
    "session_id": "ssn_01J...",
    "server_start_at": "2026-03-01T10:00:00Z"
  },
  "error": null
}
```

### `POST /sessions/end`

**Request**
```json
{
  "session_id": "ssn_01J...",
  "reason": "user_end"
}
```

**200**
```json
{
  "request_id": "...",
  "data": {
    "session_id": "ssn_01J...",
    "server_start_at": "2026-03-01T10:00:00Z",
    "server_end_at": "2026-03-01T10:24:12Z",
    "duration_seconds": 1452,
    "duration_minutes": 24.2
  },
  "error": null
}
```

## 4) Study Pack
### `POST /study-packs`

**Request**
```json
{
  "user_id": 99,
  "classroom_id": 34,
  "topic": "Đạo hàm",
  "weak_reason": "placement_accuracy_below_60",
  "evidence": {
    "document_ids": [8],
    "chunk_ids": [901, 902, 910]
  },
  "difficulty_profile": "intermediate"
}
```

**201**
```json
{
  "request_id": "...",
  "data": {
    "study_pack_id": 1201,
    "status": "ready",
    "topic": "Đạo hàm",
    "content": {
      "summary": "...",
      "outline": ["..."],
      "key_points": ["..."],
      "definitions_formulas": ["..."],
      "examples": [{"question": "...", "solution": "..."}],
      "practice": {
        "easy": [{"q": "...", "answer": "...", "explanation": "..."}],
        "medium": [{"q": "...", "answer": "...", "explanation": "..."}],
        "hard": [{"q": "...", "answer": "...", "explanation": "..."}]
      },
      "citations": [{"chunk_id": 901, "quote": "..."}]
    }
  },
  "error": null
}
```

### `GET /study-packs?user_id=99&topic=Đạo+hàm`

**200**
```json
{
  "request_id": "...",
  "data": {
    "items": [
      {
        "study_pack_id": 1201,
        "topic": "Đạo hàm",
        "created_at": "2026-03-01T10:30:00Z",
        "status": "ready"
      }
    ]
  },
  "error": null
}
```

---

## C) Danh sách file cần sửa/tạo

### Đã sửa trong đợt fix P0
- `backend/app/services/assessment_service.py`
  - Fix exclude theo learner history (không dựa `QuizSet.user_id`).
  - Áp dụng final dedup logic cho cả `diagnostic_post`.
- `backend/app/api/routes/lms.py`
  - Truyền `dedup_user_id/attempt_user_id` khi generate final qua `/v1/lms/final-exam/generate`.
- `backend/tests/test_assessment_final_requirements.py`
  - Cập nhật test cho exclude set hợp nhất (attempted + assigned + entry).

### Cần tạo/sửa tiếp theo cho full 10/10
- `backend/app/api/routes/lms.py` (export unified endpoint + session metrics surface)
- `backend/app/api/routes/exams.py` (generate-variants/download)
- `backend/app/api/routes/sessions.py` (start/end)
- `backend/app/api/routes/study_packs.py` (create/get)
- `backend/app/services/exam_variant_service.py` (batch generation + uniqueness constraints)
- `backend/app/services/exam_exporters/docx_exporter.py` (layout print-ready, multi-code)
- `backend/app/services/report_pdf_service.py` hoặc `teacher_report_export_service.py` (charts + vn fonts)
- `backend/app/services/export_xlsx_service.py` (multi-sheet gradebook)
- `backend/app/services/study_pack_service.py` (grounded generation + schema validation)
- `backend/app/services/session_service.py` (server timestamps + aggregates)
- Migrations:
  - `backend/alembic/versions/*_add_study_packs_table.py`
  - `backend/alembic/versions/*_add_export_batches_table.py`
  - `backend/alembic/versions/*_add_session_events_table.py`

---

## D) Pseudocode / implementation notes

## 1) Final exclude + anti-dup pipeline
```python
exclude_quiz_ids = set()
exclude_quiz_ids |= assigned_quiz_ids(classroom_id)
exclude_quiz_ids |= assigned_placement_ids(classroom_id)
exclude_quiz_ids |= attempted_quiz_ids(user_id, kinds=["diagnostic_pre", "entry_test", "diagnostic_post", "final_exam"])

excluded_stems = stems_from_quizzes(exclude_quiz_ids)
excluded_stems |= stems_from_attempt_history(user_id)

questions = llm_generate(..., system_hint=FINAL_HINT, excluded_stems=excluded_stems)
questions = fuzzy_filter(questions, excluded_stems, threshold=similarity_threshold)
questions = semantic_filter(questions, excluded_stems_embeddings, cosine_threshold)
if len(questions) < requested:
    questions += refill_generate_with_harder_constraints(...)

assert novelty_ratio(questions, excluded_stems) >= min_required_ratio
```

## 2) Server timer submit
```python
session = get_session(session_id)
if not session or session.ended_at:
    raise 409
now = utcnow()
elapsed = max(0, (now - session.started_at).seconds)
allowed = quiz.duration_seconds
timed_out = allowed > 0 and elapsed > allowed

attempt.time_spent_seconds = min(elapsed, allowed) if allowed > 0 else elapsed
attempt.late_submission = timed_out
# ignore payload.duration/client clock
save_attempt(attempt)
```

## 3) Export PDF/XLSX consistency
```python
report_data = build_teacher_report_from_db(classroom_id)
# single source of truth
pdf_bytes = render_pdf(report_data)
xlsx_bytes = render_xlsx(report_data)
# both read from same normalized DTO
```

## 4) Variants generation
```python
batch = create_batch(status="processing")
for code in range(1, N+1):
    variant_questions = sample_questions(
      by_difficulty=target_distribution,
      by_type=mcq_essay_ratio,
      excluded_stems=global_excluded + stems_of_previous_variants,
    )
    if unique_ratio(variant_questions, previous_variants) < min_unique_ratio:
        variant_questions = regenerate_until_pass(...)
    docx_path = export_docx(variant_questions, shuffle_questions, shuffle_options)
    save_variant_record(batch, code, docx_path)
zip_path = zip_all_variants(batch, include_answer_key)
batch.status = "ready"
```

## 5) Study pack generation w/ OCR guard
```python
evidence = retrieve_chunks(topic, user_documents)
quality = evaluate_text_quality(evidence)
if quality.score < OCR_MIN:
    return {"code": "NEED_CLEAN_TEXT", "guidance": "..."}

pack_json = llm_generate_json(schema=STUDY_PACK_SCHEMA, evidence=evidence)
assert all_items_have_citation(pack_json)
save_study_pack(pack_json, evidence_meta)
```

## 6) Study hour aggregates
```sql
-- minutes_by_day
SELECT date_trunc('day', started_at at time zone :tz) as day,
       sum(extract(epoch from (coalesce(ended_at, now()) - started_at))/60.0) as minutes
FROM session_events
WHERE user_id=:uid
GROUP BY 1;
```

---

## E) Prompt templates (JSON-stable)

## 1) Study Pack grounded prompt
### System
```text
Bạn là Learning Content Agent.
MỤC TIÊU: tạo Study Pack cá nhân hoá cho topic yếu, chỉ dùng evidence chunks được cung cấp.
RÀNG BUỘC:
- KHÔNG thêm kiến thức ngoài evidence.
- Mỗi ý chính/bài tập phải có citation chunk_id.
- Nếu evidence thiếu hoặc OCR nhiễu, trả code NEED_CLEAN_TEXT.
- Trả về JSON hợp lệ theo schema, không markdown.
```

### User
```json
{
  "task": "generate_study_pack",
  "topic": "Đạo hàm",
  "learner_level": "intermediate",
  "evidence_chunks": [
    {"chunk_id": 901, "text": "..."},
    {"chunk_id": 902, "text": "..."}
  ],
  "schema": {
    "type": "object",
    "required": ["status", "topic", "summary", "outline", "key_points", "definitions_formulas", "examples", "practice", "citations"],
    "properties": {
      "status": {"type": "string", "enum": ["ready", "NEED_CLEAN_TEXT"]},
      "topic": {"type": "string"},
      "summary": {"type": "string"},
      "outline": {"type": "array", "items": {"type": "string"}},
      "key_points": {"type": "array", "items": {"type": "object", "required": ["text", "chunk_id"], "properties": {"text": {"type": "string"}, "chunk_id": {"type": "integer"}}}},
      "definitions_formulas": {"type": "array", "items": {"type": "object", "required": ["term", "definition", "chunk_id"], "properties": {"term": {"type": "string"}, "definition": {"type": "string"}, "chunk_id": {"type": "integer"}}}},
      "examples": {"type": "array", "items": {"type": "object", "required": ["question", "solution", "chunk_id"], "properties": {"question": {"type": "string"}, "solution": {"type": "string"}, "chunk_id": {"type": "integer"}}}},
      "practice": {
        "type": "object",
        "required": ["easy", "medium", "hard"],
        "properties": {
          "easy": {"type": "array", "items": {"$ref": "#/definitions/practiceItem"}},
          "medium": {"type": "array", "items": {"$ref": "#/definitions/practiceItem"}},
          "hard": {"type": "array", "items": {"$ref": "#/definitions/practiceItem"}}
        }
      },
      "citations": {"type": "array", "items": {"type": "object", "required": ["chunk_id", "quote"], "properties": {"chunk_id": {"type": "integer"}, "quote": {"type": "string"}}}}
    },
    "definitions": {
      "practiceItem": {
        "type": "object",
        "required": ["question", "answer", "explanation", "chunk_id"],
        "properties": {
          "question": {"type": "string"},
          "answer": {"type": "string"},
          "explanation": {"type": "string"},
          "chunk_id": {"type": "integer"}
        }
      }
    }
  }
}
```

## 2) Final-new exam prompt (anti-dup)
### System
```text
Bạn là Exam Generator Agent cho bài FINAL.
BẮT BUỘC:
- Câu hỏi phải MỚI so với excluded_stems.
- Không paraphrase gần nghĩa câu đã có.
- Ưu tiên apply/analyze/evaluate.
- Mỗi câu có evidence chunk_id.
- Trả JSON đúng schema.
```

### User
```json
{
  "task": "generate_final_exam_questions",
  "topics": ["..."],
  "difficulty": {"easy": 4, "medium": 4, "hard": 2},
  "excluded_stems": ["..."],
  "similarity_threshold": 0.78,
  "schema": {
    "type": "object",
    "required": ["questions"],
    "properties": {
      "questions": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["type", "stem", "difficulty", "options", "correct_index", "explanation", "sources"],
          "properties": {
            "type": {"type": "string", "enum": ["mcq"]},
            "stem": {"type": "string"},
            "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            "options": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
            "correct_index": {"type": "integer", "minimum": 0, "maximum": 3},
            "explanation": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "object", "required": ["chunk_id"], "properties": {"chunk_id": {"type": "integer"}}}}
          }
        }
      }
    }
  }
}
```

## 3) Out-of-scope refusal prompt
### System
```text
Bạn là Tutor RAG có guardrails.
Nếu câu hỏi ngoài phạm vi tài liệu/evidence hoặc trái chính sách:
- Không bịa.
- Trả JSON với status="out_of_scope".
- Đề xuất người học cách hỏi lại trong phạm vi.
```

### User
```json
{
  "task": "tutor_answer",
  "question": "...",
  "evidence_chunks": [{"chunk_id": 1, "text": "..."}],
  "schema": {
    "type": "object",
    "required": ["status", "answer", "suggestion", "citations"],
    "properties": {
      "status": {"type": "string", "enum": ["ok", "out_of_scope", "NEED_CLEAN_TEXT"]},
      "answer": {"type": "string"},
      "suggestion": {"type": "string"},
      "citations": {"type": "array", "items": {"type": "object", "required": ["chunk_id"], "properties": {"chunk_id": {"type": "integer"}}}}
    }
  }
}
```
