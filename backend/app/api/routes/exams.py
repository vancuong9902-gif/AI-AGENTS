from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.assessment import AssessmentGenerateRequest
from app.schemas.exam import ExamAnalyzeOut, ExamGenerateFromTemplateRequest, ExamGenerateVariantsRequest, ExportFormat
from app.services import assessment_service
from app.services.exam_analyzer import analyze_assessment
from app.services.exam_exporters import export_assessment_to_docx, export_assessment_to_pdf
from app.services.exam_template_service import get_template, list_templates, template_to_assessment_counts
from app.services.exam_variant_service import export_variants_zip, generate_variants_batch


router = APIRouter(prefix="/exams", tags=["exams"])

_VARIANT_BATCHES: Dict[str, Dict[str, Any]] = {}


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
        classroom_id=payload.classroom_id,
        title=payload.title or template.name,
        level=payload.level,
        kind=template.kind,
        easy_count=counts["easy_count"],
        medium_count=counts.get("medium_count", 0),
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


@router.post("/generate-variants")
def generate_variants(payload: ExamGenerateVariantsRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    easy_count = int(payload.easy_count)
    medium_count = int(payload.medium_count)
    hard_count = int(payload.hard_count)

    if payload.template_id:
        template = get_template(payload.template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        counts = template_to_assessment_counts(template)
        easy_count = int(counts.get("easy_count", 0))
        medium_count = int(counts.get("medium_count", 0))
        hard_count = int(counts.get("hard_count", 0))

    batch = generate_variants_batch(
        db,
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        title_prefix=payload.title_prefix,
        level=payload.level,
        kind=payload.kind,
        n_variants=int(payload.n_variants),
        easy_count=easy_count,
        medium_count=medium_count,
        hard_count=hard_count,
        document_ids=[int(x) for x in (payload.document_ids or [])],
        topics=[str(x) for x in (payload.topics or [])],
        exclude_assessment_ids=[int(x) for x in (payload.exclude_assessment_ids or [])],
        similarity_threshold=float(payload.similarity_threshold),
    )
    _VARIANT_BATCHES[batch["batch_id"]] = batch
    return {
        "status": "ok",
        "data": {
            **batch,
            "export_url": f"/api/exams/variants/{batch['batch_id']}/export?format=zip",
            "assessment_ids": [int(v["assessment_id"]) for v in batch.get("variants") or []],
        },
    }


@router.get("/variants/{batch_id}/export")
def export_variants(batch_id: str, format: str = Query("zip"), db: Session = Depends(get_db)):
    if str(format).lower() != "zip":
        raise HTTPException(status_code=400, detail="Only zip format is supported")
    batch = _VARIANT_BATCHES.get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Variant batch not found")
    assessment_ids = [int(v["assessment_id"]) for v in (batch.get("variants") or [])]
    zip_path = export_variants_zip(db, batch_id=batch_id, assessment_ids=assessment_ids)
    return FileResponse(zip_path, media_type="application/zip", filename=f"variants_{batch_id}.zip")
