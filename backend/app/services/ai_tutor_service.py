from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.infra.cache import get_json, set_json
from app.schemas.tutor import TutorChatRequest
from app.services.tutor_service import tutor_chat


def _to_relevance_contract(raw: dict[str, Any], payload: TutorChatRequest) -> dict[str, Any]:
    suggestions = [
        str(x).strip()
        for x in (raw.get("suggested_questions") or raw.get("follow_up_questions") or [])
        if str(x).strip()
    ][:3]
    refs: list[str] = []
    for item in (raw.get("suggested_topics") or []):
        val = str(item).strip()
        if val and val not in refs:
            refs.append(val)
    for item in (raw.get("sources_used") or []):
        val = str(item).strip()
        if val and val not in refs:
            refs.append(val)
    if payload.topic and payload.topic.strip() and payload.topic.strip() not in refs:
        refs.insert(0, payload.topic.strip())

    is_off_topic = bool(raw.get("is_off_topic"))
    answer = str(raw.get("answer_md") or raw.get("answer") or "").strip()
    return {
        **raw,
        "is_relevant": not is_off_topic,
        "response": answer,
        "suggested_questions": suggestions,
        "references": refs[:5],
    }


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
        return {"cached": True, **_to_relevance_contract(cached, payload)}

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
    return {"cached": False, **_to_relevance_contract(response, payload)}
