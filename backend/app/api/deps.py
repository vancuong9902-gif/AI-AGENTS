"""Common FastAPI dependencies with JWT auth + safe demo fallback."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import safe_decode_token
from app.db.session import get_db
from app.models.user import User
from app.services.user_service import ensure_user_exists

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _normalize_role(role: Optional[str]) -> Optional[str]:
    if not role:
        return None
    r = str(role).strip().lower()
    if r in {"teacher", "student", "admin"}:
        return r
    return None


def _resolve_jwt_user(db: Session, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    payload = safe_decode_token(token)
    if not payload:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    token_role = _normalize_role(payload.get("role"))
    try:
        uid = int(str(sub))
    except Exception:
        return None
    user = db.query(User).filter(User.id == uid).first()
    if user is None:
        return None

    if token_role and _normalize_role(getattr(user, "role", None)) is None:
        setattr(user, "role", token_role)
    return user


def get_current_user_optional(
    request: Request = None,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Optional[User]:
    if settings.AUTH_ENABLED:
        return _resolve_jwt_user(db, token)

    if not x_user_id and request is not None:
        guest_token = request.cookies.get("guest_session")
        if guest_token:
            payload = safe_decode_token(guest_token)
            if payload and payload.get("typ") == "guest_session":
                try:
                    x_user_id = str(int(str(payload.get("sub") or "").strip()))
                except Exception:
                    x_user_id = None
                x_user_role = _normalize_role(payload.get("role"))

    if not x_user_id:
        # Demo mode fallback: avoid 401/422 on endpoints that require a user.
        if request is not None:
            return SimpleNamespace(id=2, role="student", is_active=True)
        return None
    try:
        uid = int(str(x_user_id).strip())
    except Exception:
        return None

    requested_role = _normalize_role(x_user_role)
    if requested_role == "admin":
        requested_role = "student"
    if requested_role == "teacher" and not settings.DEMO_SEED:
        requested_role = "student"

    role = requested_role or "student"
    return ensure_user_exists(db, uid, role=role)


def require_user(user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not bool(getattr(user, "is_active", True)):
        raise HTTPException(status_code=403, detail="User is inactive")
    return user


def require_teacher(user: User = Depends(require_user)) -> User:
    role = _normalize_role(getattr(user, "role", None))
    if role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher role required")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    role = _normalize_role(getattr(user, "role", None))
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def require_roles(*allowed_roles: str):
    normalized = {_normalize_role(role) for role in allowed_roles}
    normalized.discard(None)

    def _checker(user: User = Depends(require_user)) -> User:
        role = _normalize_role(getattr(user, "role", None))
        if role not in normalized:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return _checker
