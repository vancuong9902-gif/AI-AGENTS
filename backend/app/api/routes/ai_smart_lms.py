from __future__ import annotations

from fastapi import APIRouter

from app.schemas.ai_smart_lms import DashboardGateResponse, SmartLMSBlueprintResponse, TutorGuardrailRequest, TutorGuardrailResponse
from app.services.ai_smart_lms_service import SmartLMSService

router = APIRouter(prefix="/v1/ai-smart-lms", tags=["ai-smart-lms"])
service = SmartLMSService()


@router.get("/blueprint", response_model=SmartLMSBlueprintResponse)
def get_blueprint() -> SmartLMSBlueprintResponse:
    return service.build_blueprint()


@router.get("/student/course-gate", response_model=DashboardGateResponse)
def student_course_gate(has_pdf: bool = False) -> DashboardGateResponse:
    if has_pdf:
        return DashboardGateResponse(has_active_course=True, message="Course is ready. Start entry diagnostic test.")
    return DashboardGateResponse(has_active_course=False, message="No course available yet.")


@router.post("/tutor/guardrail", response_model=TutorGuardrailResponse)
def tutor_guardrail(payload: TutorGuardrailRequest) -> TutorGuardrailResponse:
    return service.validate_tutor_scope(question=payload.question, current_topic=payload.current_topic)
