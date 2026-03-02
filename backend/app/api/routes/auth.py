from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_user
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services.auth_service import authenticate_user, build_auth_response

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


@router.post("/auth/register")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    request_id = getattr(request.state, "request_id", "n/a")
    logger.info("auth.register.attempt email=%s role=%s request_id=%s", payload.email, payload.role, request_id)
    existing = db.query(User).filter(User.email == str(payload.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail={"code": "EMAIL_EXISTS", "message": "Email already exists", "field": "email"})

    role = str(payload.role or "student").strip().lower()
    if role not in {"student", "teacher"}:
        raise HTTPException(status_code=400, detail={"code": "INVALID_ROLE", "message": "Invalid role", "field": "role", "allowed": ["student", "teacher"]})

    student_code_raw = payload.student_code
    student_code = str(student_code_raw).strip() if student_code_raw else None
    if role == "student" and not student_code:
        raise HTTPException(status_code=400, detail={"code": "STUDENT_CODE_REQUIRED", "message": "student_code is required for student role", "field": "student_code"})

    u = User(
        email=str(payload.email),
        full_name=payload.full_name,
        role=role,
        student_code=student_code,
        password_hash=get_password_hash(payload.password),
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    logger.info("auth.register.success user_id=%s role=%s request_id=%s", u.id, u.role, request_id)

    token = TokenResponse(access_token=create_access_token(subject=str(u.id)))
    out = AuthResponse(token=token, user=_user_out(u)).model_dump()
    return {"request_id": request_id, "data": out, "error": None}


@router.post("/auth/login-json")
def login_json(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    request_id = getattr(request.state, "request_id", "n/a")
    user = authenticate_user(db, payload)
    out = build_auth_response(user)
    return {"request_id": request_id, "data": out, "error": None}



@router.post("/login")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    """Simple JSON login endpoint for student/teacher/admin."""
    return login_json(request=request, payload=payload, db=db)


@router.post("/auth/login")
async def login_form(request: Request, db: Session = Depends(get_db)):
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        raw_payload = await request.json()
        payload = LoginRequest.model_validate(raw_payload)
        email = str(payload.email)
        password = payload.password
    else:
        form = await request.form()
        email = str(form.get("username") or form.get("email") or "")
        password = str(form.get("password") or "")

    if not email or not password:
        raise HTTPException(status_code=422, detail="email/username and password are required")

    payload = LoginRequest(email=email, password=password)
    user = authenticate_user(db, payload)

    token = TokenResponse(access_token=create_access_token(subject=str(user.id)))
    out = {"access_token": token.access_token, "token_type": token.token_type, "role": getattr(user, "role", "student") or "student"}
    request_id = getattr(request.state, "request_id", "n/a")
    return {"request_id": request_id, "data": out, "error": None}

@router.get("/auth/me")
def me(request: Request, user: User = Depends(require_user)):
    out = _user_out(user).model_dump()
    request_id = getattr(request.state, "request_id", "n/a")
    return {"request_id": request_id, "data": out, "error": None}
