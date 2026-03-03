from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_user
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut
from app.services.auth_service import authenticate_user

router = APIRouter(tags=["auth"])
logger = logging.getLogger("app.auth")


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=int(u.id),
        email=str(u.email),
        full_name=u.full_name,
        role=getattr(u, "role", "student") or "student",
        student_code=getattr(u, "student_code", None),
        is_active=bool(getattr(u, "is_active", True)),
    )


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(
    request: Request,
    payload: RegisterRequest = Body(..., media_type="application/json"),
    db: Session = Depends(get_db),
):
    request_id = getattr(request.state, "request_id", "n/a")
    logger.info("auth.register.attempt email=%s role=%s request_id=%s", payload.email, payload.role, request_id)

    existing = db.query(User).filter(User.email == str(payload.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail={"code": "EMAIL_EXISTS", "message": "Email already exists", "field": "email"})

    user = User(
        email=str(payload.email),
        full_name=payload.name,
        role=str(payload.role),
        student_code=None,
        password_hash=get_password_hash(payload.password),
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "EMAIL_EXISTS", "message": "Email already exists", "field": "email"})

    db.refresh(user)
    return {
        "id": int(user.id),
        "email": str(user.email),
        "role": str(user.role),
        "full_name": user.full_name,
    }


@router.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    candidate_roles = ["student", "teacher", "admin"]
    user = None
    for role in candidate_roles:
        try:
            user = authenticate_user(
                db,
                LoginRequest(email=payload.email, password=payload.password, role=role),
            )
            break
        except HTTPException:
            continue

    if user is None:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    return {
        "access_token": create_access_token(subject=str(user.id)),
        "token_type": "bearer",
        "user": {
            "id": int(user.id),
            "email": str(user.email),
            "role": str(getattr(user, "role", "student") or "student"),
            "full_name": user.full_name,
        },
    }


@router.get("/auth/me")
def me(request: Request, user: User = Depends(require_user)):
    out = _user_out(user).model_dump()
    request_id = getattr(request.state, "request_id", "n/a")
    return {"request_id": request_id, "data": out, "error": None}
