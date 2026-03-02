from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_user
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, TokenResponse, UserOut

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
    logger.info("auth.register.attempt email=%s role=%s request_id=%s", payload.email, payload.role, request.state.request_id)
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
    logger.info("auth.register.success user_id=%s role=%s request_id=%s", u.id, u.role, request.state.request_id)

    token = TokenResponse(access_token=create_access_token(subject=str(u.id)))
    out = AuthResponse(token=token, user=_user_out(u)).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.post("/auth/login-json")
def login_json(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == str(payload.email)).first()
    if not u or not getattr(u, "password_hash", None):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, str(u.password_hash)):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not bool(getattr(u, "is_active", True)):
        raise HTTPException(status_code=403, detail="User is inactive")

    token = TokenResponse(access_token=create_access_token(subject=str(u.id)))
    out = AuthResponse(token=token, user=_user_out(u)).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}




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

    u = db.query(User).filter(User.email == email).first()
    if not u or not getattr(u, "password_hash", None):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(password, str(u.password_hash)):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = TokenResponse(access_token=create_access_token(subject=str(u.id)))
    out = {"access_token": token.access_token, "token_type": token.token_type, "role": getattr(u, "role", "student") or "student"}
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.get("/auth/me")
def me(request: Request, user: User = Depends(require_user)):
    out = _user_out(user).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}
