# AI Smart LMS - Production Architecture Pack

## 1) Full Folder Structure

```text
backend/
  app/
    api/routes/
      ai_smart_lms.py
    schemas/
      ai_smart_lms.py
    services/
      ai_smart_lms_service.py
    services/exam_exporters/
      docx_exporter.py
      pdf_exporter.py
      export_xlsx_service.py
frontend/
  src/
    main.js
    styles.css
```

## 2) Backend Code (Implemented)

- Role-based dashboard gate endpoint: `/api/v1/ai-smart-lms/student/course-gate`
- Tutor scope guardrail endpoint: `/api/v1/ai-smart-lms/tutor/guardrail`
- Architecture blueprint endpoint: `/api/v1/ai-smart-lms/blueprint`

All endpoints are mounted in `backend/app/main.py`.

## 3) Frontend Code (Implemented)

- Login flow with JWT token persistence.
- Role-based dashboard routing:
  - Teacher dashboard with upload/class/exam/analytics feature cards.
  - Student dashboard with no-course state and adaptive-learning cards.
- Standard logout button for both dashboards.

## 4) Database Schema

Existing schema already includes and is migration-backed for:
- users, classrooms, documents, quiz_sets, questions, attempts, learning_plan, class_reports.

Recommended additions for strict AI Smart LMS naming alignment:
- `learning_roadmaps`
- `learning_sessions`
- `student_results`

## 5) AI Prompt Templates

Prompt groups to keep in `backend/app/ai/prompt_templates/`:
- roadmap_generation.md
- exam_generation.md
- student_evaluation.md
- tutor_restriction.md

Constraint prompt for tutor:

```text
You are AI Tutor for AI Smart LMS.
Only answer using uploaded PDF context and current roadmap topic.
If user asks unrelated question, refuse politely and redirect to allowed topic.
```

## 6) PDF Processing Strategy

1. Parse with PyMuPDF first (preserves layout better for Vietnamese).
2. Apply fallback OCR when text density is too low.
3. Normalize Unicode (NFC) to avoid Vietnamese glyph mismatch.
4. Run heading detection and semantic chunking.
5. Build chapter/topic/subtopic graph before generation.

## 7) Example API Endpoints

- `GET /api/v1/ai-smart-lms/blueprint`
- `GET /api/v1/ai-smart-lms/student/course-gate?has_pdf=false`
- `POST /api/v1/ai-smart-lms/tutor/guardrail`

## 8) Example JSON Responses

`GET /student/course-gate?has_pdf=false`

```json
{
  "has_active_course": false,
  "message": "No course available yet."
}
```

`POST /tutor/guardrail`

```json
{
  "accepted": false,
  "reason": "I can only answer questions tied to uploaded material and current topic."
}
```

## 9) Example Word Export Implementation

Implemented module: `backend/app/services/exam_exporters/docx_exporter.py`.
Use this exporter to generate printable exam docs from randomized question sets.

## 10) Example PDF Export Implementation

Implemented module: `backend/app/services/report_pdf_service.py` with report templates in `backend/app/resources/`.
Use for final evaluation reports per student/class.

## 11) Example Excel Export Implementation

Implemented module: `backend/app/services/export_xlsx_service.py`.
Use for gradebook export and aggregate assessment summary.
