from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.core.config import settings
from app.db.session import get_db
from app.infra.event_bus import RedisEventBus
from app.models.agent_log import AgentLog
from app.models.user import User

router = APIRouter(tags=["admin"])


@router.get("/admin/agent-dashboard")
def get_agent_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    events_last_24h = (
        db.query(func.count(AgentLog.id))
        .filter(AgentLog.created_at >= since)
        .scalar()
        or 0
    )

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

    recent_rows = (
        db.query(AgentLog)
        .order_by(AgentLog.created_at.desc())
        .limit(20)
        .all()
    )
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
