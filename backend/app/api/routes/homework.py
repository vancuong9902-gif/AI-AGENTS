from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.homework import (
    HomeworkGradeRequest,
    HomeworkGradeResult,
    HomeworkSubmitRequest,
    HomeworkSubmitResponse,
)
from app.services.homework_service import grade_homework
from app.services.learning_plan_storage_service import grade_homework_from_plan

router = APIRouter(tags=["homework"])


@router.post("/homework/grade")
def homework_grade(request: Request, payload: HomeworkGradeRequest, db: Session = Depends(get_db)):
    result = grade_homework(
        db,
        user_id=int(payload.user_id),
        stem=payload.stem,
        answer_text=payload.answer_text,
        max_points=int(payload.max_points or 10),
        rubric=payload.rubric,
        sources=payload.sources,
    )

    out = HomeworkGradeResult(**result).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.post("/homework/{hw_id}/submit")
def homework_submit(
    request: Request,
    hw_id: int,
    payload: HomeworkSubmitRequest,
    db: Session = Depends(get_db),
):
    try:
        data = grade_homework_from_plan(
            db,
            plan_id=int(hw_id),
            user_id=int(payload.user_id),
            day_index=int(payload.day_index),
            answer_text=str(payload.answer_text or ""),
            mcq_answers={str(payload.question_id): int(payload.chosen_index)},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    feedback = None
    for item in (data.get("mcq_breakdown") or []):
        if str(item.get("question_id")) == str(payload.question_id):
            feedback = item.get("feedback")
            break
    if not feedback:
        feedback = data.get("feedback") or {}

    out = HomeworkSubmitResponse(question_id=str(payload.question_id), feedback=feedback).model_dump(exclude_none=True)
    return {"request_id": request.state.request_id, "data": out, "error": None}
