from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, require_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User

from app.api.deps import require_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(tags=["notifications"])


def _notification_out(row: Notification) -> dict:
    return {
        "id": int(row.id),
        "user_id": int(row.user_id),
        "type": str(row.type.value if hasattr(row.type, "value") else row.type),
        "title": row.title,
        "message": row.message,
        "payload_json": row.payload_json or {},
        "is_read": bool(row.is_read),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/notifications")
def get_unread_notifications(request: Request, user_id: int, db: Session = Depends(get_db)):
@router.get("/notifications/my")
def get_my_notifications(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == int(user.id))
        .order_by(Notification.created_at.desc())
        .all()
    )
    return {"request_id": request.state.request_id, "data": [_notification_out(r) for r in rows], "error": None}


@router.get("/notifications/my")
def get_my_notifications(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == int(user.id))
        .order_by(Notification.created_at.desc())
        .all()
    )
    return {
        "request_id": request.state.request_id,
        "data": {
            "items": [_notification_out(r) for r in rows],
            "unread_count": sum(1 for r in rows if not bool(r.is_read)),
        },
    return {
        "request_id": request.state.request_id,
        "data": [
            {
                "id": int(r.id),
                "user_id": int(r.user_id),
                "type": str(getattr(r.type, "value", r.type)),
                "message": r.message,
                "title": r.title,
                "payload_json": r.payload_json or {},
                "is_read": bool(r.is_read),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "error": None,
    }


class MarkReadPayload(BaseModel):
    is_read: bool = True


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(
@router.post("/notifications/{notification_id}/mark-read")
def mark_my_notification_read(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    user: User = Depends(require_user),
):
    row = (
        db.query(Notification)
        .filter(Notification.id == int(notification_id), Notification.user_id == int(user.id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    if user and int(row.user_id) != int(user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    row.is_read = True
    db.commit()
    db.refresh(row)
    return {"request_id": request.state.request_id, "data": {"id": int(row.id), "is_read": bool(row.is_read)}, "error": None}


@router.post("/notifications/{notification_id}/mark-read")
def mark_notification_read_v2(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    row = db.query(Notification).filter(Notification.id == int(notification_id), Notification.user_id == int(user.id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.is_read = True
    db.commit()
    db.refresh(row)
    return {"request_id": request.state.request_id, "data": _notification_out(row), "error": None}
    return {
        "request_id": request.state.request_id,
        "data": {"id": int(row.id), "is_read": True},
        "error": None,
    }
