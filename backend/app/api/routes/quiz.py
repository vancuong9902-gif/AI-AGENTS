from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.quiz import QuizGenerateRequest, QuizSubmitRequest
from app.services.quiz_service import generate_quiz_with_rag, get_or_create_practice_quiz_set_by_topic, grade_and_store_attempt

router = APIRouter(tags=['quiz'])


@router.post('/quiz/generate')
def quiz_generate(request: Request, payload: QuizGenerateRequest, db: Session = Depends(get_db)):
    data = generate_quiz_with_rag(db=db, payload=payload)
    return {'request_id': request.state.request_id, 'data': data, 'error': None}


@router.post('/quiz/{quiz_id}/submit')
def quiz_submit(request: Request, quiz_id: int, payload: QuizSubmitRequest, db: Session = Depends(get_db)):
    data = grade_and_store_attempt(db=db, quiz_id=quiz_id, payload=payload)
    return {'request_id': request.state.request_id, 'data': data, 'error': None}


@router.get('/quiz/by-topic')
def quiz_by_topic(
    request: Request,
    topic_id: int = Query(..., ge=1),
    level: str = Query(..., pattern='^(easy|medium|hard)$'),
    user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    data = get_or_create_practice_quiz_set_by_topic(db=db, topic_id=topic_id, level=level, user_id=user_id)
    return {'request_id': request.state.request_id, 'data': data, 'error': None}
