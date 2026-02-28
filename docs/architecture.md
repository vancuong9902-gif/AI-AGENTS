# AI-AGENTS LMS Architecture (current + upgraded MVP)

## End-to-end flow

```mermaid
flowchart LR
A[Teacher Upload PDF] --> B[/api/documents/upload]
B --> C[document_pipeline.extract_and_chunk_with_report]
C --> D[Vietnamese normalize + chunk]
D --> E[topic_service.extract_topics]
E --> F[(Document/DocumentChunk/DocumentTopic)]
F --> G[Teacher chọn topics]
G --> H[/api/quizzes/placement or /api/quizzes/final]
H --> I[assessment_service.generate_assessment]
I --> J[(QuizSet + Questions)]
J --> K[/api/attempts/start]
K --> L[Student làm bài + timer]
L --> M[/api/attempts/{id}/submit]
M --> N[assessment_service.submit_assessment]
N --> O[lms_service.score_breakdown + classify_student_level]
O --> P[recommendations + assignments]
P --> Q[/api/students/{id}/recommendations]
O --> R[/api/teacher/reports]
R --> S[Teacher dashboard/report]
```

## Backend modules
- `document_pipeline.py`: extractor candidates, scoring theo coverage/quality, OCR fallback, normalize tiếng Việt.
- `topic_service.py`: tách topics từ heading/chapter, gán chunk range, enrich detail.
- `assessment_service.py`: tạo đề + nộp bài + chấm điểm.
- `lms_service.py`: breakdown theo topic/difficulty, phân loại năng lực, recommendation rule-based.
- `api/routes/lms.py`: orchestration endpoints cho teacher/student report.

## Frontend modules
- `App.jsx` + `App.css`: AppShell (sidebar + topbar + main).
- `ui/theme.css`: design tokens + utility class + component-level primitives.
- Pages trọng tâm MVP:
  - `Upload`: drag/drop + upload progress/result + pdf report summary.
  - `FileLibrary`: search/filter, empty/loading/error states, topic actions.
  - `Quiz`: timer, progress, submit confirm, result breakdown.

## Critical gaps identified before implementation
### 1) Data model / API gaps
- Chưa có endpoint alias theo contract MVP (`/quizzes/placement`, `/attempts/start`, `/teacher/reports`, ...).
- Timer lifecycle thiếu endpoint start/submit chuẩn theo `attempt_id`.
- Recommendation API chưa có endpoint riêng theo `student_id`.

### 2) AI logic gaps
- `pdf_report` chưa có trường `extractor_chosen` + `selection_reason` rõ ràng để giải thích quyết định.
- Thiếu test “topic split stability” cho case heading tiếng Việt dài.

### 3) Frontend UX/UI gaps
- Thiếu state chuẩn hóa ở vài màn (loading/empty/error không đồng nhất).
- Theme/token chưa đủ utility classes cho dashboard SaaS thống nhất.
- Chưa có reusable components cho Banner/Modal/Tabs/Table/Pagination/Skeleton.
