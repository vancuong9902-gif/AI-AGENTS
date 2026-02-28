"""Common FastAPI dependencies (demo-first).

Mode A (default):
  - No email/password login
  - No JWT
  - Frontend sends demo headers: X-User-Id, X-User-Role

We auto-create a minimal User row if missing so foreign keys won't fail.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.services.user_service import ensure_user_exists


def _normalize_role(role: Optional[str]) -> Optional[str]:
    if not role:
        return None
    r = str(role).strip().lower()
    if r in {"teacher", "student"}:
        return r
    return None


def get_current_user_optional(
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Optional[User]:
    """Return current user from demo headers.

    If headers are missing, returns None (caller may allow anonymous access).
    """

    if not x_user_id:
        return None

    try:
        uid = int(str(x_user_id).strip())
    except Exception:
        return None

    role = _normalize_role(x_user_role) or "student"
    return ensure_user_exists(db, uid, role=role)


def require_user(user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_teacher(user: User = Depends(require_user)) -> User:
    role = _normalize_role(getattr(user, "role", None))
    if role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher role required")
    return user
