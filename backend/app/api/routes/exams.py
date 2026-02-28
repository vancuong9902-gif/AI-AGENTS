from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.assessment import AssessmentGenerateRequest
from app.schemas.exam import ExamAnalyzeOut, ExamGenerateFromTemplateRequest, ExportFormat
from app.services import assessment_service
from app.services.exam_analyzer import analyze_assessment
from app.services.exam_exporters import export_assessment_to_docx, export_assessment_to_pdf
from app.services.exam_template_service import get_template, list_templates, template_to_assessment_counts


router = APIRouter(prefix="/exams", tags=["exams"])


@router.get("/templates")
def get_templates() -> Dict[str, Any]:
    """List built-in exam templates."""
    return {
        "templates": [t.model_dump() for t in list_templates()],
    }


@router.post("/generate-from-template")
def generate_from_template(
    payload: ExamGenerateFromTemplateRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Generate an assessment using a pre-defined template.

    This is a thin wrapper on top of existing assessment generation logic,
    providing a flexible template input format for teachers.
    """
    template = get_template(payload.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    counts = template_to_assessment_counts(template)
    req = AssessmentGenerateRequest(
        teacher_id=payload.teacher_id,
        title=payload.title or template.name,
        level=payload.level,
        kind=template.kind,
        easy_count=counts["easy_count"],
        hard_count=counts["hard_count"],
        document_ids=payload.document_ids,
        topics=payload.topics,
    )

    try:
        assessment = assessment_service.generate_assessment(db, req.model_dump())
        return {"status": "ok", "data": assessment}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{assessment_id}/analyze", response_model=ExamAnalyzeOut)
def analyze(
    assessment_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Analyze an existing assessment (coverage, difficulty, bloom distribution)."""
    try:
        quiz_set = db.query(assessment_service.QuizSet).filter(assessment_service.QuizSet.id == assessment_id).first()
        kind = quiz_set.kind if quiz_set else ""
        assessment = assessment_service.get_assessment(db, assessment_id=assessment_id)
        return analyze_assessment(assessment, kind=kind)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{assessment_id}/export")
def export_exam(
    assessment_id: int,
    format: ExportFormat = Query("pdf"),
    db: Session = Depends(get_db),
):
    """Export an assessment to PDF or DOCX."""
    try:
        quiz_set = db.query(assessment_service.QuizSet).filter(assessment_service.QuizSet.id == assessment_id).first()
        kind = quiz_set.kind if quiz_set else ""
        assessment = assessment_service.get_assessment(db, assessment_id=assessment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if format == "pdf":
        path = export_assessment_to_pdf(assessment, kind=kind)
        return FileResponse(path, media_type="application/pdf", filename=f"assessment_{assessment_id}.pdf")
    else:
        path = export_assessment_to_docx(assessment, kind=kind)
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"assessment_{assessment_id}.docx",
        )
