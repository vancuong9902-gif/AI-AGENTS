from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_user
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, TokenResponse, UserOut


router = APIRouter(tags=["auth"])


def _normalize_role(role: str | None) -> str:
    r = (role or "student").strip().lower()
    if r not in {"student", "teacher"}:
        raise HTTPException(status_code=400, detail="Invalid role. Use 'student' or 'teacher'.")
    return r


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=int(u.id),
        email=str(u.email),
        full_name=u.full_name,
        role=getattr(u, "role", "student") or "student",
        is_active=bool(getattr(u, "is_active", True)),
    )


@router.post("/auth/register")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    role = _normalize_role(payload.role)
    existing = db.query(User).filter(User.email == str(payload.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    u = User(
        email=str(payload.email),
        full_name=payload.full_name,
        role=role,
        password_hash=get_password_hash(payload.password),
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)

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


@router.post("/auth/login")
def login_form(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm uses fields: username, password
    u = db.query(User).filter(User.email == str(form_data.username)).first()
    if not u or not getattr(u, "password_hash", None):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(form_data.password, str(u.password_hash)):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = TokenResponse(access_token=create_access_token(subject=str(u.id)))
    out = {"access_token": token.access_token, "token_type": token.token_type}
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.get("/auth/me")
def me(request: Request, user: User = Depends(require_user)):
    out = _user_out(user).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}
