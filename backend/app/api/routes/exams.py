from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
import random
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, get_db
from app.schemas.exam import (
    BatchExamGenerateRequest,
    ExamAnalyzeOut,
    ExamGenerateFromTemplateRequest,
    ExamGenerateVariantsRequest,
    MultiVariantGenerateRequest,
    ExportFormat,
)
from app.services import assessment_service
from app.services.exam_analyzer import analyze_assessment
from app.services.exam_exporters import export_assessment_to_docx, export_assessment_to_pdf, export_batch_to_zip, export_multi_variant_docx
from app.services.exam_template_service import get_template, list_templates, template_to_assessment_counts
from app.services.exam_variant_service import export_variants_zip, generate_variants_batch


def _allocate_counts(total: int, distribution: Dict[str, float], keys: List[str]) -> Dict[str, int]:
    weights = [max(0.0, float(distribution.get(k, 0.0))) for k in keys]
    if sum(weights) <= 0:
        weights = [1.0 for _ in keys]

    raw = [float(total) * w / float(sum(weights)) for w in weights]
    counts = [int(x) for x in raw]
    remainder = int(total) - sum(counts)

    order = sorted(range(len(keys)), key=lambda i: (raw[i] - counts[i]), reverse=True)
    for idx in order[: max(0, remainder)]:
        counts[idx] += 1

    return {keys[i]: counts[i] for i in range(len(keys))}


def _paper_code(index: int, style: str) -> str:
    if style == "NUM":
        return f"{index + 1:02d}"
    return chr(65 + (index % 26))


def _shuffle_question_options(questions: List[Dict[str, Any]]) -> None:
    for q in questions:
        if str(q.get("type") or "").lower() != "mcq":
            continue
        options = list(q.get("options") or [])
        if len(options) < 2:
            continue
        try:
            correct_index = int(q.get("correct_index"))
        except Exception:
            correct_index = 0

        indexed = list(enumerate(options))
        random.shuffle(indexed)
        q["options"] = [opt for _, opt in indexed]

        new_correct = 0
        for new_idx, (old_idx, _) in enumerate(indexed):
            if old_idx == correct_index:
                new_correct = new_idx
                break
        q["correct_index"] = new_correct


def _build_counts(payload: BatchExamGenerateRequest) -> Dict[str, int]:
    total = int(payload.questions_per_paper)
    mcq_total = int(round(total * float(payload.mcq_ratio)))
    essay_total = int(total - mcq_total)

    distribution = payload.difficulty_distribution or {}
    mcq_counts = _allocate_counts(mcq_total, distribution, ["easy", "medium", "hard"])

    essay_dist = {"medium": float(distribution.get("medium", 0.0)), "hard": float(distribution.get("hard", 0.0))}
    if essay_dist["medium"] <= 0 and essay_dist["hard"] <= 0:
        essay_counts = {"easy": 0, "medium": 0, "hard": essay_total}
    else:
        essay_part = _allocate_counts(essay_total, essay_dist, ["medium", "hard"])
        essay_counts = {"easy": 0, "medium": essay_part["medium"], "hard": essay_part["hard"]}

    return {
        "easy": mcq_counts["easy"] + essay_counts["easy"],
        "medium": mcq_counts["medium"] + essay_counts["medium"],
        "hard": mcq_counts["hard"] + essay_counts["hard"],
    }


def _fingerprint_question(question: Dict[str, Any]) -> str:
    stem = " ".join(str(question.get("stem") or "").lower().split())
    options = "|".join(" ".join(str(o).lower().split()) for o in (question.get("options") or []))
    return f"{stem}::{options}"


def _stable_seed(*parts: Any) -> int:
    import hashlib

    raw = "|".join(str(p) for p in parts)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


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

    try:
        assessment = assessment_service.generate_assessment(
            db,
            teacher_id=int(payload.teacher_id),
            classroom_id=int(payload.classroom_id),
            title=payload.title or template.name,
            level=payload.level,
            kind=template.kind,
            easy_count=int(counts["easy_count"]),
            medium_count=int(counts["medium_count"]),
            hard_mcq_count=int(counts["hard_mcq_count"]),
            hard_count=int(counts["hard_count"]),
            document_ids=[int(x) for x in (payload.document_ids or [])],
            topics=[str(x) for x in (payload.topics or [])],
        )
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
    hard_mcq_count = 0

    if payload.template_id:
        template = get_template(payload.template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        counts = template_to_assessment_counts(template)
        easy_count = int(counts.get("easy_count", 0))
        medium_count = int(counts.get("medium_count", 0))
        hard_mcq_count = int(counts.get("hard_mcq_count", 0))
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
        hard_mcq_count=hard_mcq_count,
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


@router.post("/batch-generate")
def batch_generate_exams(
    payload: BatchExamGenerateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    teacher_id = int(getattr(current_user, "id", 0) or payload.teacher_id or 1)
    counts = _build_counts(payload)
    excluded_quiz_ids: List[int] = []
    papers: List[Dict[str, Any]] = []

    for idx in range(int(payload.num_papers)):
        assessment = assessment_service.generate_assessment(
            db,
            teacher_id=teacher_id,
            classroom_id=int(payload.classroom_id),
            title=f"{payload.title} - Đề {_paper_code(idx, payload.paper_code_style)}",
            level="intermediate",
            kind="midterm",
            easy_count=int(counts["easy"]),
            medium_count=int(counts["medium"]),
            hard_count=int(counts["hard"]),
            document_ids=[int(x) for x in (payload.document_ids or [])],
            topics=[str(x) for x in (payload.topics or [])],
            exclude_quiz_ids=excluded_quiz_ids,
            similarity_threshold=float(payload.similarity_threshold),
        )
        questions = list(assessment.get("questions") or [])
        random.shuffle(questions)
        _shuffle_question_options(questions)

        code = _paper_code(idx, payload.paper_code_style)
        assessment["questions"] = questions
        assessment["paper_code"] = code
        assessment["paper_title"] = f"Đề {code}"
        papers.append(assessment)

        quiz_set_id = assessment.get("assessment_id")
        if quiz_set_id is not None:
            excluded_quiz_ids.append(int(quiz_set_id))

    zip_path = export_batch_to_zip(papers, include_answer_key=bool(payload.include_answer_key))
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"de_thi_batch_{int(payload.classroom_id)}.zip",
    )


@router.post("/generate-multi-variant")
def generate_multi_variant(payload: MultiVariantGenerateRequest, db: Session = Depends(get_db)):
    template = get_template(payload.template_id) if payload.template_id else None
    counts = {"easy_count": int(payload.easy_count), "medium_count": int(payload.medium_count), "hard_count": int(payload.hard_count), "hard_mcq_count": 0}
    if template:
        counts = template_to_assessment_counts(template)

    generated: List[Dict[str, Any]] = []
    seen_fingerprints: set[str] = set()
    excluded_quiz_ids: List[int] = []
    for i in range(int(payload.num_variants)):
        assessment = assessment_service.generate_assessment(
            db,
            teacher_id=int(payload.teacher_id),
            classroom_id=int(payload.classroom_id),
            title=f"Đề {i + 1:02d}",
            level="intermediate",
            kind="midterm",
            easy_count=int(counts.get("easy_count", 0)),
            medium_count=int(counts.get("medium_count", 0)),
            hard_mcq_count=int(counts.get("hard_mcq_count", 0)),
            hard_count=int(counts.get("hard_count", 0)),
            document_ids=[int(x) for x in (payload.document_ids or [])],
            topics=[str(x) for x in (payload.topics or [])],
            similarity_threshold=float(payload.similarity_threshold),
            exclude_quiz_ids=excluded_quiz_ids,
        )

        for _ in range(2):
            questions = list(assessment.get("questions") or [])
            duplicates = [q for q in questions if _fingerprint_question(q) in seen_fingerprints]
            if not duplicates:
                break
            assessment = assessment_service.generate_assessment(
                db,
                teacher_id=int(payload.teacher_id),
                classroom_id=int(payload.classroom_id),
                title=f"Đề {i + 1:02d}",
                level="intermediate",
                kind="midterm",
                easy_count=int(counts.get("easy_count", 0)),
                medium_count=int(counts.get("medium_count", 0)),
                hard_mcq_count=int(counts.get("hard_mcq_count", 0)),
                hard_count=int(counts.get("hard_count", 0)),
                document_ids=[int(x) for x in (payload.document_ids or [])],
                topics=[str(x) for x in (payload.topics or [])],
                similarity_threshold=float(payload.similarity_threshold),
                exclude_quiz_ids=excluded_quiz_ids,
            )

        variant_questions = list(assessment.get("questions") or [])
        for q in variant_questions:
            seen_fingerprints.add(_fingerprint_question(q))
        assessment["paper_code"] = f"{i + 1:02d}"
        generated.append(assessment)
        if assessment.get("assessment_id"):
            excluded_quiz_ids.append(int(assessment["assessment_id"]))

    docx_path = export_multi_variant_docx(variants=generated, title="Bộ đề nhiều mã")
    return FileResponse(
        path=str(docx_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"multi_variant_{payload.classroom_id}.docx",
    )
