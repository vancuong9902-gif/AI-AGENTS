from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, TokenResponse, UserOut


def authenticate_user(db: Session, payload: LoginRequest) -> User:
    """Authenticate a user via email/password.

    Raises:
        HTTPException(400): invalid credentials
        HTTPException(403): inactive account
    """
    email = str(payload.email).strip().lower()
    password = str(payload.password)

    user = db.query(User).filter(User.email == email).first()
    if not user or not getattr(user, "password_hash", None):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if not verify_password(password, str(user.password_hash)):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if not bool(getattr(user, "is_active", True)):
        raise HTTPException(status_code=403, detail="User is inactive")
    return user


def build_auth_response(user: User) -> dict:
    token = TokenResponse(access_token=create_access_token(subject=str(user.id)))
    out = AuthResponse(
        token=token,
        user=UserOut(
            id=int(user.id),
            email=str(user.email),
            full_name=user.full_name,
            role=getattr(user, "role", "student") or "student",
            student_code=getattr(user, "student_code", None),
            is_active=bool(getattr(user, "is_active", True)),
        ),
    )
    return out.model_dump()
