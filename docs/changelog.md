# Changelog (MVP upgrade)

## Backend
- Bổ sung docs audit: `architecture.md`, `requirements-mapping.md`.
- Nâng `pdf_report` với `extractor_chosen`, `selection_reason`, `page_coverage`, `chunk_count`.
- Thêm API contract aliases:
  - `POST /quizzes/placement`
  - `POST /quizzes/final`
  - `POST /attempts/start`
  - `POST /attempts/{id}/submit`
  - `GET /students/{id}/recommendations`
  - `GET /teacher/reports`
- Bổ sung test topic split stability.

## Frontend
- Chuẩn hóa design system trong `ui/theme.css` (tokens + utilities + reusable styles).
- Nâng AppShell: mobile drawer toggle + focus ring + role-group menu.
- Redesign trang `Upload`, `Library`, `Quiz` theo cấu trúc page header + states.
- API client ưu tiên `VITE_API_URL` (fallback `VITE_API_BASE_URL`).
