from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.tutor import TutorChatRequest, TutorGenerateQuestionsRequest
from app.services.tutor_service import tutor_chat, tutor_generate_questions

router = APIRouter(tags=["tutor"])


@router.post("/tutor/chat")
def chat(request: Request, payload: TutorChatRequest, db: Session = Depends(get_db)):
    data = tutor_chat(
        db=db,
        user_id=payload.user_id,
        question=payload.question,
        topic=payload.topic,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
    )

    # Safety: ensure response is JSON-serializable.
    # Some DB meta fields (or upstream libs) may contain `bytes`, which breaks JSON encoding.
    safe = jsonable_encoder(
        data,
        custom_encoder={
            bytes: lambda b: b.decode("utf-8", errors="ignore"),
            bytearray: lambda b: bytes(b).decode("utf-8", errors="ignore"),
            memoryview: lambda b: bytes(b).decode("utf-8", errors="ignore"),
        },
    )
    return {"request_id": request.state.request_id, "data": safe, "error": None}


@router.post("/tutor/generate-questions")
def generate_questions(request: Request, payload: TutorGenerateQuestionsRequest, db: Session = Depends(get_db)):
    """Practice mode: generate questions for the student to answer.

    Key requirement: questions must be derived from the document contents for the chosen topic
    (no fixed/preset question framework).
    """
    data = tutor_generate_questions(
        db=db,
        user_id=payload.user_id,
        topic=payload.topic,
        level=payload.level,
        question_count=payload.question_count,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
    )

    safe = jsonable_encoder(
        data,
        custom_encoder={
            bytes: lambda b: b.decode("utf-8", errors="ignore"),
            bytearray: lambda b: bytes(b).decode("utf-8", errors="ignore"),
            memoryview: lambda b: bytes(b).decode("utf-8", errors="ignore"),
        },
    )
    return {"request_id": request.state.request_id, "data": safe, "error": None}


