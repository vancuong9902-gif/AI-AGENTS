from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.infra.cache import get_json, set_json
from app.schemas.tutor import TutorChatRequest
from app.services.tutor_service import tutor_chat


def _cache_key(payload: TutorChatRequest) -> str:
    raw = "|".join(
        [
            str(payload.user_id),
            (payload.question or "").strip().lower(),
            (payload.topic or "").strip().lower(),
            ",".join(str(i) for i in (payload.document_ids or [])),
            ",".join((payload.allowed_topics or [])),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"tutor:chat:v1:{digest}"


def run_tutor_chat(db: Session, payload: TutorChatRequest) -> dict[str, Any]:
    key = _cache_key(payload)
    cached = get_json(key)
    if cached is not None:
        return {"cached": True, **cached}

    response = tutor_chat(
        db=db,
        user_id=payload.user_id,
        question=payload.question,
        topic=payload.topic,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
        allowed_topics=payload.allowed_topics,
        assessment_id=payload.assessment_id,
        attempt_id=payload.attempt_id,
        exam_mode=payload.exam_mode,
        timed_test=payload.timed_test,
    )
    set_json(key, response, ttl_seconds=180)
    return {"cached": False, **response}
