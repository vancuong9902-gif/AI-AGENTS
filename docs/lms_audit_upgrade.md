# Audit & Upgrade Plan — AI Learning Agent (Target 10/10)

## A) Chấm điểm hiện trạng (thang 10)

### Tổng điểm hiện trạng: **7.3 / 10**

| Hạng mục | Trọng số | Điểm hiện tại | Lý do chấm điểm (evidence trong repo) |
|---|---:|---:|---|
| 1) Ingestion PDF + OCR + quality gate | 1.2 | 1.0 | Có multi-extractor + OCR fallback + quality gate (`document_pipeline.py`, `documents.py`). Tuy nhiên logic quality report chưa chuẩn hóa 1 contract chung cho toàn hệ. |
| 2) Sửa lỗi tiếng Việt/phông + OCR spacing | 1.0 | 0.5 | Có module sửa font/spacing; nhưng file `vietnamese_font_fix.py` đang bị **duplicate definition/map** gây sai convert VNI (test đỏ). |
| 3) Topic split grounded theo heading + tách PRACTICE | 1.2 | 0.9 | Có pipeline topic + reject appendix/bài tập ở nhiều nhánh; vẫn còn rủi ro tách sai nếu heading yếu và chưa enforce schema “đủ fields” cứng ở DB. |
| 4) Placement test (3 difficulty + timer server-side + auto-grade + breakdown) | 1.3 | 1.0 | Có generate/submit/breakdown/timer server-side. Gap: gate “approved topic only” có thể block luồng thực tế khi topic mới chưa duyệt kịp. |
| 5) Adaptive phân loại + giao học liệu + anti-duplicate history | 1.0 | 0.7 | Có classify 4 mức + learning path. Thiếu bảng lịch sử fingerprint/similarity bền vững cấp câu hỏi để chống trùng xuyên kỳ/lớp. |
| 6) Tutor AI RAG-only + từ chối khéo khi thiếu evidence | 1.0 | 0.6 | Có off-topic gate + refusal prompt. Nhưng `tutor_service.py` có **2 hàm trùng tên `_is_question_on_topic_llm`** (signature conflict), dễ lỗi runtime/test. |
| 7) Final exam mới tinh + anti-dup mạnh + khác cấu trúc đầu vào | 1.1 | 0.7 | Có novelty enforcer và similarity threshold. Gap: novelty hiện chủ yếu SequenceMatcher, chưa có semantic ANN + chưa lưu “question usage ledger” chuẩn. |
| 8) Teacher analytics + export PDF/Excel + classroom report | 0.8 | 0.7 | Có dashboard/service export PDF/XLSX; cần chuẩn hóa KPI bắt buộc (pre→post gain, weak-topic cohort, phân phối level theo lớp). |
| 9) Sinh đề Word N mã đề + đáp án + giảm trùng giữa mã đề | 0.9 | 0.8 | Có batch generate + ZIP DOCX/PDF route. Gap: thiếu seed persist per paper và báo cáo overlap định lượng giữa mã đề. |
| 10) Tính ổn định, grounded, tái lập (seed/log/fingerprint) | 0.5 | 0.4 | Đã có một phần `generation_seed/excluded_from_quiz_ids`; nhưng thiếu chuẩn log/fingerprint tập trung cho mọi luồng generate. |

---

## B) Gap/Bug cụ thể trong repo (file/func/route + cách sửa)

### P0 bugs (phải sửa ngay)
- [ ] **Duplicate function name gây sai contract on-topic gate**
  - **Vị trí:** `backend/app/services/tutor_service.py` — có 2 hàm `_is_question_on_topic_llm` với signature khác nhau.
  - **Hành vi lỗi:** test gọi positional bị văng `TypeError`; hành vi on-topic gate không ổn định theo runtime import order.
  - **Sửa cụ thể:** giữ 1 hàm chuẩn duy nhất (`_is_question_on_topic_llm_v2`), route/service gọi qua wrapper thống nhất; xóa hàm cũ.

- [ ] **Module font tiếng Việt bị ghi đè map do duplicate constants/defs**
  - **Vị trí:** `backend/app/services/vietnamese_font_fix.py` (nhiều block `_VNI_BASE_MAP`, `_VNI_TONE_MAP`, `detect_vni_typing` bị định nghĩa lại).
  - **Hành vi lỗi:** convert VNI (`Toa1n ho5c`) không ra Unicode chuẩn, test đỏ.
  - **Sửa cụ thể:** tách module thành 3 phần rõ (`detect`, `map`, `convert`), chỉ giữ 1 bộ map canonical; thêm regression tests cho `a61n`, `Toa1n ho5c lo7p 10`.

- [ ] **Gate “approved topics only” chặn generation quá sớm**
  - **Vị trí:** `backend/app/services/assessment_service.py` trong `generate_assessment()`.
  - **Hành vi lỗi:** nếu teacher chọn topic mới extract nhưng chưa approved -> raise `ValueError`, làm fail flow tạo placement.
  - **Sửa cụ thể:** cho phép chế độ `strict_topic_approval` (default false với teacher draft), ghi cảnh báo + audit log thay vì hard fail.

### P1 gaps (ảnh hưởng chất lượng 10/10)
- [ ] **Thiếu cột chuẩn `difficulty` + `topic_id` trực tiếp trên `questions`**
  - **Vị trí:** `backend/app/models/question.py`.
  - **Hành vi:** breakdown phải suy diễn từ metadata/bloom, khó query thống kê chuẩn và chống trùng theo topic-difficulty.
  - **Sửa:** thêm cột `difficulty`, `topic_id`, index `(quiz_set_id, topic_id, difficulty)`.

- [ ] **Chưa có bảng lịch sử sử dụng câu hỏi/fingerprint/similarity bền vững**
  - **Vị trí liên quan:** hiện rải rác ở `quiz_sets.excluded_from_quiz_ids`, dedup trong service.
  - **Hành vi:** chống trùng xuyên pre/final/luyện chưa đủ mạnh khi scale nhiều lớp.
  - **Sửa:** thêm `question_fingerprints`, `question_usage_history` + ANN vector index.

- [ ] **Final novelty enforcer mới lexical-heavy**
  - **Vị trí:** `backend/app/services/final_exam_novelty_enforcer.py`.
  - **Hành vi:** bỏ sót câu paraphrase mạnh.
  - **Sửa:** hybrid similarity (lexical + embedding cosine), threshold theo loại câu hỏi.

- [ ] **Batch exam chưa lưu seed mỗi mã đề**
  - **Vị trí:** `backend/app/api/routes/exams.py` (`batch_generate_exams`).
  - **Hành vi:** khó tái lập đúng mã đề khi cần audit/in lại.
  - **Sửa:** nhận `seed_base`; mỗi đề `seed = hash(seed_base + paper_code)` và persist vào `quiz_sets.generation_seed`.

### P2 hardening
- [ ] Chuẩn hóa response “grounded status” (`OK | NEED_MORE_EVIDENCE | NEED_CLEAN_TEXT`) cho toàn bộ agent endpoints.
- [ ] Thêm quality report chi tiết per page/ extractor drift để giáo viên biết trang nào OCR vỡ.

---

## C) Roadmap nâng cấp đạt 10/10 (P0/P1/P2)

### P0 (1–2 tuần)
- [ ] Refactor `tutor_service.py`: loại duplicate `_is_question_on_topic_llm`, contract 1 schema.
- [ ] Cleanup `vietnamese_font_fix.py`: bỏ định nghĩa trùng, fix converter VNI triệt để.
- [ ] Sửa `generate_assessment()` cho topic approval mode mềm + audit log.
- [ ] Bổ sung “grounding guard” bắt buộc: thiếu evidence => trả `NEED_MORE_EVIDENCE` hoặc `NEED_CLEAN_TEXT`, không generate cưỡng bức.

### P1 (2–4 tuần)
- [ ] Migration DB: thêm `questions.difficulty`, `questions.topic_id`.
- [ ] Tạo bảng `question_fingerprints`, `question_usage_history`, `assignment_history` (chi tiết ở phần D).
- [ ] Nâng anti-dup final/pre/luyện bằng hybrid similarity (Sequence + cosine embedding).
- [ ] Persist seed/log toàn bộ luồng generate (pre/final/batch variants).

### P2 (4–6 tuần)
- [ ] Chuẩn hóa analytics KPI + classroom cohort reports.
- [ ] Export suite v2: PDF report có chart chuẩn + Excel multi-sheet chuẩn class/test/student.
- [ ] Exam Paper Agent v2: overlap-control giữa mã đề theo ngân sách trùng cho phép (vd <15%).

---

## D) Thiết kế dữ liệu (DB/schema)

### 1) Lưu difficulty / bloom / topic_id cho câu hỏi

```sql
ALTER TABLE questions
  ADD COLUMN difficulty VARCHAR(10) NOT NULL DEFAULT 'medium',
  ADD COLUMN topic_id INT NULL REFERENCES document_topics(id);

CREATE INDEX ix_questions_quiz_topic_diff
  ON questions (quiz_set_id, topic_id, difficulty);

CREATE INDEX ix_questions_bloom
  ON questions (bloom_level);
```

### 2) Lưu lịch sử câu hỏi đã dùng (fingerprint + similarity)

```sql
CREATE TABLE question_fingerprints (
  id BIGSERIAL PRIMARY KEY,
  normalized_stem TEXT NOT NULL,
  stem_fingerprint CHAR(64) NOT NULL UNIQUE,
  embedding VECTOR(768) NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE question_usage_history (
  id BIGSERIAL PRIMARY KEY,
  question_id INT NOT NULL REFERENCES questions(id),
  fingerprint_id BIGINT NOT NULL REFERENCES question_fingerprints(id),
  user_id INT NULL REFERENCES users(id),
  classroom_id INT NULL REFERENCES classrooms(id),
  quiz_set_id INT NOT NULL REFERENCES quiz_sets(id),
  usage_type VARCHAR(20) NOT NULL, -- pre/final/practice/homework
  used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  similarity_to_prev NUMERIC(5,4) NULL,
  duplicate_blocked BOOLEAN NOT NULL DEFAULT false,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX ix_q_usage_user_class_used_at
  ON question_usage_history (user_id, classroom_id, used_at DESC);
CREATE INDEX ix_q_usage_usage_type
  ON question_usage_history (usage_type);
```

### 3) Lưu lịch sử giao bài theo học sinh/lớp

```sql
CREATE TABLE assignment_history (
  id BIGSERIAL PRIMARY KEY,
  student_id INT NOT NULL REFERENCES users(id),
  classroom_id INT NOT NULL REFERENCES classrooms(id),
  topic_id INT NULL REFERENCES document_topics(id),
  assignment_kind VARCHAR(20) NOT NULL, -- material/practice/final_review
  source_quiz_set_id INT NULL REFERENCES quiz_sets(id),
  learning_plan_id INT NULL REFERENCES learning_plans(id),
  assigned_payload JSONB NOT NULL,
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  due_at TIMESTAMPTZ NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'assigned'
);

CREATE INDEX ix_assignment_history_student_topic
  ON assignment_history (student_id, topic_id, assigned_at DESC);
CREATE INDEX ix_assignment_history_classroom
  ON assignment_history (classroom_id, assigned_at DESC);
```

---

## E) Thiết kế API endpoint mới / cần sửa

### 1) Ingestion quality gate report
`POST /api/documents/upload`

**Response bổ sung (mẫu):**
```json
{
  "status": "OK",
  "document_id": 101,
  "quality_gate": {
    "status": "OK",
    "quality_score": 0.87,
    "broken_font_detected": false,
    "extractor_rank": [
      {"name": "pymupdf_words", "score": 0.87, "coverage": 0.94},
      {"name": "pdfplumber", "score": 0.79, "coverage": 0.88}
    ],
    "page_alerts": []
  }
}
```

### 2) Topic extraction grounded
`GET /api/documents/{document_id}/topics?detail=1`

```json
{
  "status": "OK",
  "topics": [
    {
      "topic_id": 55,
      "title": "Chương 2: Hàm số bậc nhất",
      "summary": "...",
      "outline": ["2.1 ...", "2.2 ..."],
      "keywords": ["hàm số", "đồ thị"],
      "key_points": ["..."],
      "definitions": ["..."],
      "examples": ["..."],
      "formulas": ["y=ax+b"],
      "practice": {
        "exercises": ["..."],
        "answers": ["..."]
      },
      "grounding": {"status": "OK", "evidence_chunk_ids": [812, 813]}
    }
  ]
}
```

### 3) Placement/final generation có anti-dup + seed
`POST /api/lms/placement/generate`
`POST /api/lms/final/generate`

```json
{
  "teacher_id": 1,
  "classroom_id": 2,
  "topic_ids": [55, 56],
  "difficulty": {"easy": 4, "medium": 4, "hard": 2},
  "duration_seconds": 1800,
  "similarity_threshold": 0.78,
  "seed": "class2-pre-2026-01"
}
```

```json
{
  "status": "OK",
  "assessment_id": 5001,
  "generation_seed": "class2-pre-2026-01",
  "grounding": {"status": "OK"},
  "dedup_report": {"blocked": 3, "max_similarity": 0.71}
}
```

### 4) Submit attempt + breakdown chuẩn
`POST /api/lms/attempts/{assessment_id}/submit`

```json
{
  "status": "OK",
  "score": 78,
  "breakdown": {
    "by_topic": [{"topic_id": 55, "percent": 62.5}],
    "by_difficulty": [{"difficulty": "hard", "percent": 40}],
    "by_bloom": [{"bloom": "analyze", "percent": 55}]
  },
  "student_level": "trung_binh",
  "recommendations": [...]
}
```

### 5) Tutor ask (RAG-only)
`POST /api/tutor/ask`

```json
{
  "question": "...",
  "topic_id": 55,
  "document_ids": [101],
  "exam_mode": false
}
```

```json
{
  "status": "NEED_MORE_EVIDENCE",
  "action": "ASK_TOPIC_OR_DOC",
  "answer_md": "Mình chưa đủ dữ liệu để trả lời chắc chắn..."
}
```

### 6) Batch exam paper DOCX
`POST /api/exams/batch-generate`

```json
{
  "teacher_id": 1,
  "classroom_id": 2,
  "title": "Đề ôn tập HK1",
  "num_papers": 5,
  "questions_per_paper": 30,
  "mcq_ratio": 0.7,
  "difficulty_distribution": {"easy": 0.3, "medium": 0.4, "hard": 0.3},
  "seed_base": "HK1-2026-A",
  "include_answer_key": true
}
```

---

## F) Acceptance Test (Given/When/Then) — tối thiểu 15 test

1. **PDF text-based tốt**
   - Given PDF có text layer chuẩn
   - When upload
   - Then `quality_gate.status=OK`, score >= 0.75.

2. **PDF scan mờ**
   - Given PDF scan mờ nhiều trang
   - When upload
   - Then fallback OCR chạy; nếu score < ngưỡng trả `NEED_CLEAN_TEXT` + instructions.

3. **Lỗi font legacy**
   - Given text chứa `Toa1n ho5c`/ký tự vỡ
   - When normalize
   - Then trả Unicode đúng và không mất dấu.

4. **Topic bám heading**
   - Given sách có Chương/Mục rõ
   - When extract topics
   - Then title topic map đúng heading, không bịa tên mới.

5. **Không tách Bài tập thành topic độc lập**
   - Given chương có phần Bài tập/Đáp án
   - When topic split
   - Then phần này nằm trong `practice` của topic.

6. **Topic schema đầy đủ**
   - Given extract thành công
   - When trả topic detail
   - Then có đủ summary/outline/keywords/key_points/definitions/examples/formulas.

7. **Generate placement 3 độ khó**
   - Given chọn topics
   - When tạo đề pre-test
   - Then số lượng câu easy/medium/hard đúng cấu hình.

8. **Timer server-side enforce**
   - Given attempt quá deadline
   - When submit
   - Then hệ thống chấm theo trạng thái timeout (không tin thời gian client).

9. **MCQ chấm ngay**
   - Given nộp bài trắc nghiệm
   - When submit
   - Then nhận điểm và đáp án đúng/sai tức thì.

10. **Essay auto-grade + fallback**
    - Given LLM bật/tắt
    - When submit essay
    - Then bật: chấm LLM có rubric; tắt: heuristic fallback hợp lý.

11. **Breakdown đầy đủ**
    - Given có kết quả
    - When xem kết quả
    - Then có breakdown theo topic + difficulty + bloom.

12. **Phân loại 4 mức**
    - Given 4 profile điểm khác nhau
    - When classify
    - Then ra đúng 4 mức (yếu/tb/khá/giỏi).

13. **Tutor off-topic refusal**
    - Given câu hỏi ngoài tài liệu
    - When hỏi tutor
    - Then trả từ chối khéo + gợi ý hỏi lại đúng cách.

14. **Tutor thiếu evidence**
    - Given retrieval không đủ
    - When hỏi tutor
    - Then trả `NEED_MORE_EVIDENCE` (hoặc NEED_MORE_INFO theo contract) và không bịa.

15. **Final exam không trùng pre/practice/history**
    - Given có lịch sử câu đã dùng
    - When generate final
    - Then câu mới đều dưới similarity threshold so với history.

16. **Final khác cấu trúc pre-test**
    - Given đề đầu vào đã có cấu trúc A
    - When generate final
    - Then final có pattern khác (thứ tự/loại câu/tỷ lệ) nhưng vẫn đúng topics.

17. **Teacher report PDF**
    - Given lớp có dữ liệu đủ
    - When export PDF
    - Then file có chart giờ học, điểm theo thời gian, pre→post gain, top yếu.

18. **Gradebook Excel**
    - Given dữ liệu nhiều lớp/bài/học sinh
    - When export XLSX
    - Then có sheet theo lớp, theo bài kiểm tra, theo học sinh.

19. **Batch DOCX nhiều mã đề**
    - Given yêu cầu N mã đề
    - When generate batch
    - Then mỗi mã có seed khác nhau, có đáp án, overlap giữa mã đề dưới ngưỡng.

---

## G) Prompt hệ thống

## 1) Master Prompt — Orchestrator Agent

**Mục tiêu:** điều phối các agent con theo pipeline grounded, fail-safe.

**Input schema:**
```json
{
  "request_id": "string",
  "stage": "ingestion|topic|assessment|tutor|reporting|exam_paper",
  "payload": {},
  "policy": {"grounded_required": true, "seed": "string"}
}
```

**Output schema:**
```json
{
  "status": "OK|NEED_CLEAN_TEXT|NEED_MORE_EVIDENCE|ERROR",
  "next_stage": "string|null",
  "result": {},
  "audit": {"seed": "string", "agent": "string", "notes": []}
}
```

**Self-check:**
- Có evidence không?
- Có vi phạm difficulty mapping/bloom mapping không?
- Có duplicate theo fingerprint/similarity không?

**Từ chối khi:** payload thiếu trường bắt buộc hoặc evidence không đủ.

---

## 2) Ingestion Agent Prompt

**Mục tiêu:** extract text ổn định + quality gate + font/spacing fix.

**Input schema:**
```json
{"document_id": 1, "file_path": "...", "force_ocr": false}
```

**Output schema:**
```json
{
  "status": "OK|NEED_CLEAN_TEXT|ERROR",
  "text": "...",
  "quality_report": {
    "score": 0.0,
    "broken_font": false,
    "extractor_scores": [],
    "page_alerts": []
  }
}
```

**Self-check:** score >= threshold, không còn chuỗi lỗi font phổ biến, coverage đủ.

**Từ chối khi:** score thấp hoặc OCR vỡ nặng => `NEED_CLEAN_TEXT`.

---

## 3) Topic Agent Prompt

**Mục tiêu:** split topic theo heading sách, tách PRACTICE trong từng topic.

**Input schema:**
```json
{"clean_text": "...", "document_id": 1, "max_topics": 40}
```

**Output schema:**
```json
{
  "status": "OK|NEED_MORE_EVIDENCE|NEED_CLEAN_TEXT",
  "topics": [
    {
      "title": "...",
      "summary": "...",
      "outline": [],
      "keywords": [],
      "key_points": [],
      "definitions": [],
      "examples": [],
      "formulas": [],
      "practice": {"exercises": [], "answers": []},
      "grounding": {"evidence_chunk_ids": []}
    }
  ]
}
```

**Self-check:** title phải match heading; không tạo topic riêng cho Bài tập/Đáp án.

**Từ chối khi:** không đủ heading/evidence để xác định topic chắc chắn.

---

## 4) Assessment Agent Prompt

**Mục tiêu:** sinh pre/final đủ 3 độ khó, anti-dup, enforce timer metadata.

**Input schema:**
```json
{
  "mode": "diagnostic_pre|final",
  "topics": [],
  "difficulty_target": {"easy": 4, "medium": 4, "hard": 2},
  "duration_seconds": 1800,
  "exclude_fingerprints": [],
  "similarity_threshold": 0.78,
  "seed": "..."
}
```

**Output schema:**
```json
{
  "status": "OK|NEED_MORE_EVIDENCE|NEED_CLEAN_TEXT|ERROR",
  "assessment": {"questions": [], "duration_seconds": 1800},
  "dedup_report": {"blocked": 0, "max_similarity": 0.0}
}
```

**Self-check:**
- đủ số câu theo easy/medium/hard,
- bloom mapping đúng,
- không trùng history > threshold.

**Từ chối khi:** thiếu evidence hoặc không thể đạt anti-dup mà vẫn đủ coverage.

---

## 5) Tutor Agent Prompt

**Mục tiêu:** trả lời RAG-only; từ chối khéo nếu ngoài scope/thiếu evidence.

**Input schema:**
```json
{"question": "...", "topic": "...", "evidence_chunks": [], "exam_mode": false}
```

**Output schema:**
```json
{
  "status": "OK|NEED_MORE_EVIDENCE",
  "action": "ANSWER|REFUSE_OUT_OF_SCOPE|ASK_TOPIC_OR_DOC",
  "answer_md": "...",
  "sources": []
}
```

**Self-check:** không có claim nào thiếu evidence.

**Từ chối khi:** off-topic hoặc evidence thấp.

---

## 6) Reporting Agent Prompt

**Mục tiêu:** tạo analytics + export PDF/Excel theo lớp.

**Input schema:**
```json
{"classroom_id": 2, "date_range": {"from": "...", "to": "..."}}
```

**Output schema:**
```json
{
  "status": "OK|ERROR",
  "kpis": {"study_hours": [], "score_trend": [], "pre_post_gain": 0},
  "exports": {"pdf_path": "...", "xlsx_path": "..."}
}
```

**Self-check:** đủ 5 chart bắt buộc + bảng chi tiết.

**Từ chối khi:** thiếu dữ liệu tối thiểu theo lớp.

---

## 7) Exam Paper Agent Prompt

**Mục tiêu:** sinh N mã đề DOCX (hoặc ZIP) với seed khác nhau, hạn chế trùng.

**Input schema:**
```json
{
  "num_papers": 5,
  "questions_per_paper": 30,
  "mix": "mcq|essay|mixed",
  "difficulty_distribution": {"easy": 0.3, "medium": 0.4, "hard": 0.3},
  "seed_base": "HK1-2026"
}
```

**Output schema:**
```json
{
  "status": "OK|NEED_MORE_EVIDENCE|ERROR",
  "papers": [{"code": "A", "seed": "...", "overlap_ratio": 0.12}],
  "export": {"docx_zip": "...", "answer_key": "..."}
}
```

**Self-check:** mỗi đề seed khác nhau; overlap dưới ngưỡng; có answer key.

**Từ chối khi:** không đủ ngân hàng câu để đạt ngưỡng trùng.

---

## Checklist hoàn tất (để đạt 10/10)
- [ ] Sửa triệt để duplicate defs ở `tutor_service.py`.
- [ ] Sửa triệt để duplicate map/defs ở `vietnamese_font_fix.py`.
- [ ] Bổ sung DB schema history/fingerprint/topic-difficulty.
- [ ] Chuẩn hóa grounded status cho mọi agent endpoint.
- [ ] Persist seed + dedup report cho pre/final/batch.
- [ ] Bổ sung acceptance tests 1→19 vào CI gate.
