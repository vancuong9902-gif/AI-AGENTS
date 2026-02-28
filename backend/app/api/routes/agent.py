from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.agent import (
    AgentPhase1Out,
    EntryTestGenerateRequest,
    EntryTestGenerateOut,
    EntryTestSubmitRequest,
    EntryTestSubmitOut,
    FinalExamGenerateRequest,
    FinalExamGenerateOut,
    FinalExamSubmitRequest,
    FinalExamSubmitOut,
    TopicExercisesGenerateRequest,
    TopicExercisesGenerateOut,
    TopicExercisesSubmitRequest,
    TopicExercisesSubmitOut,
)
from app.services.agent_service import (
    build_phase1_document_analysis,
    generate_exam,
    grade_exam,
    final_exam_analytics,
    generate_topic_exercises,
    postprocess_topic_attempt,
)

router = APIRouter(tags=["agent"])


@router.get("/agent/documents/{document_id}/phase1", response_model=AgentPhase1Out)
def phase1_document_analysis(
    request: Request,
    document_id: int,
    include_llm: int = 1,
    max_topics: int = 40,
    db: Session = Depends(get_db),
):
    data = build_phase1_document_analysis(db, document_id=int(document_id), include_llm=bool(include_llm), max_topics=int(max_topics))
    safe = jsonable_encoder(data)
    return safe


@router.post("/agent/entry-test/generate", response_model=EntryTestGenerateOut)
def entry_test_generate(request: Request, payload: EntryTestGenerateRequest, db: Session = Depends(get_db)):
    data = generate_exam(
        db,
        user_id=int(payload.user_id),
        kind="entry_test",
        document_ids=[int(x) for x in (payload.document_ids or [])],
        topics=[str(x) for x in (payload.topics or [])],
        language=str(payload.language or "vi"),
        rag_query=(payload.rag_query or None),
    )
    out = {
        "quiz_id": int(data["quiz_id"]),
        "kind": str(data["kind"]),
        "title": "Entry Test",
        "questions": data["questions"],
    }
    safe = jsonable_encoder(out)
    return safe


@router.post("/agent/entry-test/{quiz_id}/submit", response_model=EntryTestSubmitOut)
def entry_test_submit(request: Request, quiz_id: int, payload: EntryTestSubmitRequest, db: Session = Depends(get_db)):
    answers = [a.model_dump() for a in (payload.answers or [])]
    data = grade_exam(
        db,
        quiz_id=int(quiz_id),
        user_id=int(payload.user_id),
        duration_sec=int(payload.duration_sec or 0),
        answers=answers,
    )
    safe = jsonable_encoder(data)
    return safe


@router.post("/agent/final-exam/generate", response_model=FinalExamGenerateOut)
def final_exam_generate(request: Request, payload: FinalExamGenerateRequest, db: Session = Depends(get_db)):
    data = generate_exam(
        db,
        user_id=int(payload.user_id),
        kind="final_exam",
        document_ids=[int(x) for x in (payload.document_ids or [])],
        topics=[str(x) for x in (payload.topics or [])],
        language=str(payload.language or "vi"),
        rag_query=(payload.rag_query or None),
    )
    out = {
        "quiz_id": int(data["quiz_id"]),
        "kind": str(data["kind"]),
        "title": "Final Exam",
        "questions": data["questions"],
    }
    safe = jsonable_encoder(out)
    return safe


@router.post("/agent/final-exam/{quiz_id}/submit", response_model=FinalExamSubmitOut)
def final_exam_submit(request: Request, quiz_id: int, payload: FinalExamSubmitRequest, db: Session = Depends(get_db)):
    answers = [a.model_dump() for a in (payload.answers or [])]
    data = grade_exam(
        db,
        quiz_id=int(quiz_id),
        user_id=int(payload.user_id),
        duration_sec=int(payload.duration_sec or 0),
        answers=answers,
    )
    analytics = final_exam_analytics(data.get("breakdown") or [])
    data["analytics"] = analytics
    safe = jsonable_encoder(data)
    return safe


@router.post("/agent/topic-exercises/generate", response_model=TopicExercisesGenerateOut)
def topic_exercises_generate(request: Request, payload: TopicExercisesGenerateRequest, db: Session = Depends(get_db)):
    data = generate_topic_exercises(
        db,
        user_id=int(payload.user_id),
        topic_id=int(payload.topic_id),
        language=str(payload.language or "vi"),
        difficulty=(str(payload.difficulty) if payload.difficulty else None),
    )
    safe = jsonable_encoder(data)
    return safe


@router.post("/agent/topic-exercises/{quiz_id}/submit", response_model=TopicExercisesSubmitOut)
def topic_exercises_submit(request: Request, quiz_id: int, payload: TopicExercisesSubmitRequest, db: Session = Depends(get_db)):
    answers = [a.model_dump() for a in (payload.answers or [])]
    graded = grade_exam(
        db,
        quiz_id=int(quiz_id),
        user_id=int(payload.user_id),
        duration_sec=int(payload.duration_sec or 0),
        answers=answers,
    )
    data = postprocess_topic_attempt(
        db,
        user_id=int(payload.user_id),
        topic_id=int(payload.topic_id),
        quiz_id=int(quiz_id),
        attempt_payload=graded,
    )
    safe = jsonable_encoder(data)
    return safe
