from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter

from app.learning_engine.presentation.dependencies import build_learning_service
from app.learning_engine.presentation.schemas import (
    DocumentIngestRequest,
    EntranceTestRequest,
    ExerciseRequest,
    FinalReportRequest,
    LevelEvaluationRequest,
    ProgressUpdateRequest,
)

router = APIRouter(prefix="/teacher-ai", tags=["teacher-ai-v2"])


@lru_cache(maxsize=1)
def _service():
    return build_learning_service()


@router.post("/documents/ingest")
async def ingest_document(payload: DocumentIngestRequest):
    topics = await _service().ingest_document(payload.document_id, payload.content)
    return {"topics": topics}


@router.post("/assessments/entrance")
async def generate_entrance_test(payload: EntranceTestRequest):
    questions = await _service().build_entrance_assessment(payload.student_id, payload.document_id)
    return {"questions": questions}


@router.post("/students/evaluate")
async def evaluate_student(payload: LevelEvaluationRequest):
    return await _service().evaluate_and_generate_path(payload.student_id, payload.document_id, payload.entrance_score)


@router.post("/exercises/generate")
async def generate_exercise(payload: ExerciseRequest):
    return await _service().generate_exercise(payload.topic_id, payload.objective, payload.difficulty)


@router.post("/progress/update")
async def update_progress(payload: ProgressUpdateRequest):
    return await _service().update_progress(payload.student_id, payload.completion_rate, payload.mastery_by_topic)


@router.post("/reports/final")
async def generate_final_report(payload: FinalReportRequest):
    return await _service().create_final_report(
        student_id=payload.student_id,
        level=payload.level,
        completion_rate=payload.completion_rate,
        mastery_by_topic=payload.mastery_by_topic,
        exam_score=payload.exam_score,
    )
