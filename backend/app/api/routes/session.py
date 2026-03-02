from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.core.config import settings
from app.core.security import create_access_token, safe_decode_token
from app.db.session import get_db
from app.models.user import User
from app.services.user_service import ensure_user_exists

router = APIRouter(tags=["session"])

_SESSION_COOKIE = "guest_session"
_ALLOWED_ROLES = {"student", "teacher"}


class StartSessionRequest(BaseModel):
    role: str


@router.post("/session/start")
def start_guest_session(payload: StartSessionRequest, response: Response, db: Session = Depends(get_db)):
    role = str(payload.role or "").strip().lower()
    if role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    generated_id = uuid.uuid4().int % 1_000_000_000
    user = ensure_user_exists(db, generated_id, role=role)

    token = create_access_token(
        subject=str(user.id),
        expires_minutes=24 * 60,
        extra={"role": role, "typ": "guest_session"},
    )
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        max_age=24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )

    return {"data": {"id": user.id, "role": role}}


@router.post("/session/end")
def end_guest_session(response: Response):
    response.delete_cookie(_SESSION_COOKIE, path="/")
    return {"data": {"ok": True}}


@router.get("/session/me")
def get_guest_session(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    if user:
        return {"data": {"id": user.id, "role": user.role}}

    raw = request.cookies.get(_SESSION_COOKIE)
    payload = safe_decode_token(raw) if raw else None
    if not payload or payload.get("typ") != "guest_session":
        raise HTTPException(status_code=401, detail="Session not found")

    try:
        uid = int(str(payload.get("sub") or "").strip())
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Session not found") from exc

    role = str(payload.get("role") or "student").strip().lower()
    if role not in _ALLOWED_ROLES:
        role = "student"
    resolved = ensure_user_exists(db, uid, role=role)
    return {"data": {"id": resolved.id, "role": resolved.role}}
