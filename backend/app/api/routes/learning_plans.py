from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.learning_plans import (
    HomeworkGradeFromPlanRequest,
    LearningPlanLatestResponse,
    TaskCompleteRequest,
)
from app.services.learning_plan_storage_service import (
    get_latest_plan,
    get_homework_submission,
    grade_homework_from_plan,
    set_task_completion,
)


router = APIRouter(tags=["learning_plans"])


@router.get("/learning-plans/{user_id}/latest")
def learning_plan_latest(request: Request, user_id: int, db: Session = Depends(get_db), classroom_id: int | None = None):
    data = get_latest_plan(db, user_id=int(user_id), classroom_id=classroom_id)
    if not data:
        raise HTTPException(status_code=404, detail="No learning plan found")
    out = LearningPlanLatestResponse(**data).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.post("/learning-plans/{plan_id}/tasks/complete")
def learning_plan_task_complete(
    request: Request,
    plan_id: int,
    payload: TaskCompleteRequest,
    db: Session = Depends(get_db),
):
    try:
        data = set_task_completion(
            db,
            plan_id=int(plan_id),
            day_index=int(payload.day_index),
            task_index=int(payload.task_index),
            completed=bool(payload.completed),
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/learning-plans/{plan_id}/homework/grade")
def learning_plan_homework_grade(
    request: Request,
    plan_id: int,
    payload: HomeworkGradeFromPlanRequest,
    db: Session = Depends(get_db),
):
    try:
        data = grade_homework_from_plan(
            db,
            plan_id=int(plan_id),
            user_id=int(payload.user_id),
            day_index=int(payload.day_index),
            answer_text=str(payload.answer_text or ""),
            mcq_answers=getattr(payload, "mcq_answers", None),
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/learning-plans/{plan_id}/homework/{user_id}/{day_index}")
def learning_plan_homework_get(
    request: Request,
    plan_id: int,
    user_id: int,
    day_index: int,
    db: Session = Depends(get_db),
):
    data = get_homework_submission(db, plan_id=int(plan_id), user_id=int(user_id), day_index=int(day_index))
    if not data:
        raise HTTPException(status_code=404, detail="No homework submission found")
    return {"request_id": request.state.request_id, "data": data, "error": None}
