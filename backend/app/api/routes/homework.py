from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.homework import HomeworkGradeRequest, HomeworkGradeResult
from app.services.homework_service import grade_homework

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
