from __future__ import annotations

from fastapi.encoders import jsonable_encoder

from app.db.session import SessionLocal
from app.schemas.tutor import TutorChatRequest
from app.services.ai_tutor_service import run_tutor_chat


def task_tutor_chat(payload: dict) -> dict:
    """RQ task: execute tutor chat logic off the request thread."""

    db = SessionLocal()
    try:
        chat_payload = TutorChatRequest.model_validate(payload)
        data = run_tutor_chat(db, chat_payload)
        safe = jsonable_encoder(
            data,
            custom_encoder={
                bytes: lambda b: b.decode("utf-8", errors="ignore"),
                bytearray: lambda b: bytes(b).decode("utf-8", errors="ignore"),
                memoryview: lambda b: bytes(b).decode("utf-8", errors="ignore"),
            },
        )
        return {"ok": True, "data": safe}
    finally:
        db.close()
