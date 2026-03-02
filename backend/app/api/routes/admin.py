from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_teacher
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import get_db
from app.infra.event_bus import RedisEventBus
from app.models.agent_log import AgentLog
from app.models.user import User
from app.schemas.auth import AdminCreateStudentRequest, AdminCreateTeacherRequest, AdminUserPatchRequest, UserOut

router = APIRouter(tags=["admin"])


def _to_user_out(user: User) -> dict:
    return UserOut(
        id=int(user.id),
        email=str(user.email),
        full_name=user.full_name,
        role=str(user.role or "student"),
        student_code=getattr(user, "student_code", None),
        is_active=bool(getattr(user, "is_active", True)),
    ).model_dump()


@router.post("/admin/users/teachers")
def create_teacher(
    request: Request,
    payload: AdminCreateTeacherRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=get_password_hash(payload.password),
        role="teacher",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"request_id": request.state.request_id, "data": _to_user_out(user), "error": None}


@router.post("/admin/users/students")
def create_student(
    request: Request,
    payload: AdminCreateStudentRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        student_code=payload.student_code.strip(),
        password_hash=get_password_hash(payload.password),
        role="student",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"request_id": request.state.request_id, "data": _to_user_out(user), "error": None}


@router.get("/admin/users")
def list_users(
    request: Request,
    q: str | None = Query(default=None),
    role: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.email.ilike(like), User.full_name.ilike(like), User.student_code.ilike(like)))
    if role in {"student", "teacher", "admin"}:
        query = query.filter(User.role == role)

    total = query.count()
    rows = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "request_id": request.state.request_id,
        "data": {"items": [_to_user_out(r) for r in rows], "total": int(total), "limit": limit, "offset": offset},
        "error": None,
    }


@router.patch("/admin/users/{user_id}")
def patch_user(
    request: Request,
    user_id: int,
    payload: AdminUserPatchRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.is_active is not None:
        user.is_active = bool(payload.is_active)
    if payload.password:
        user.password_hash = get_password_hash(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.student_code is not None:
        user.student_code = payload.student_code.strip()

    if user.role == "student" and not str(user.student_code or "").strip():
        raise HTTPException(status_code=400, detail="student_code is required for student role")

    db.add(user)
    db.commit()
    db.refresh(user)
    return {"request_id": request.state.request_id, "data": _to_user_out(user), "error": None}


@router.get("/admin/agent-dashboard")
def get_agent_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    events_last_24h = db.query(func.count(AgentLog.id)).filter(AgentLog.created_at >= since).scalar() or 0

    rows = (
        db.query(
            AgentLog.agent_name,
            AgentLog.status,
            func.count(AgentLog.id).label("cnt"),
            func.avg(AgentLog.duration_ms).label("avg_ms"),
        )
        .filter(AgentLog.created_at >= since)
        .group_by(AgentLog.agent_name, AgentLog.status)
        .all()
    )

    agents: dict[str, dict] = {}
    for agent_name, status, cnt, avg_ms in rows:
        cur = agents.setdefault(str(agent_name), {"success": 0, "failed": 0, "timeout": 0, "avg_ms": 0})
        cur[str(status)] = int(cnt or 0)
        if avg_ms is not None:
            cur["avg_ms"] = int(round(float(avg_ms)))

    recent_rows = db.query(AgentLog).order_by(AgentLog.created_at.desc()).limit(20).all()
    recent_events = [
        {
            "id": int(r.id),
            "event_id": r.event_id,
            "event_type": r.event_type,
            "agent_name": r.agent_name,
            "user_id": r.user_id,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "output_summary": r.output_summary or {},
        }
        for r in recent_rows
    ]

    pending_events = 0
    try:
        pending_events = RedisEventBus(settings.REDIS_URL).pending_count()
    except Exception:
        pending_events = 0

    return {
        "request_id": request.state.request_id,
        "data": {
            "events_last_24h": int(events_last_24h),
            "agents": agents,
            "recent_events": recent_events,
            "pending_events": int(pending_events),
        },
        "error": None,
    }
