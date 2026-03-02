from __future__ import annotations

from dataclasses import dataclass

from app.schemas.ai_smart_lms import BlueprintSection, SmartLMSBlueprintResponse, TutorGuardrailResponse


@dataclass(slots=True)
class SmartLMSService:
    def build_blueprint(self) -> SmartLMSBlueprintResponse:
        sections = [
            BlueprintSection(
                title="folder_structure",
                payload={
                    "backend": [
                        "app/api/routes",
                        "app/controllers",
                        "app/services",
                        "app/repositories",
                        "app/ai/prompt_templates",
                        "app/exports",
                    ],
                    "frontend": [
                        "src/features/auth",
                        "src/features/teacher",
                        "src/features/student",
                        "src/components/states",
                        "src/components/charts",
                    ],
                },
            ),
            BlueprintSection(
                title="database_schema",
                payload={
                    "tables": [
                        "users",
                        "classes",
                        "class_members",
                        "documents",
                        "learning_roadmaps",
                        "learning_sessions",
                        "exam_sets",
                        "exam_questions",
                        "exam_attempts",
                        "student_results",
                    ]
                },
            ),
            BlueprintSection(
                title="pdf_processing_strategy",
                payload={
                    "flow": [
                        "pymupdf text extraction",
                        "fallback OCR for scanned pages",
                        "Unicode normalization for Vietnamese",
                        "semantic chunking by heading graph",
                        "topic graph + exercise generation",
                    ]
                },
            ),
            BlueprintSection(
                title="exports",
                payload={
                    "word": "python-docx exporter in app/services/exam_exporters/docx_exporter.py",
                    "pdf": "reportlab/jinja2 html template service in app/services/report_pdf_service.py",
                    "excel": "openpyxl exporter in app/services/export_xlsx_service.py",
                },
            ),
        ]
        return SmartLMSBlueprintResponse(sections=sections)

    def validate_tutor_scope(self, question: str, current_topic: str) -> TutorGuardrailResponse:
        normalized_question = question.lower()
        normalized_topic = current_topic.lower()
        accepted = normalized_topic in normalized_question
        if accepted:
            return TutorGuardrailResponse(
                accepted=True,
                reason="Question is grounded in current roadmap topic.",
            )
        return TutorGuardrailResponse(
            accepted=False,
            reason="I can only answer questions tied to uploaded material and current topic.",
        )
