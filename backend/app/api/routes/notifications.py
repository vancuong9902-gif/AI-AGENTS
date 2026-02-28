from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.notification import Notification


router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def get_unread_notifications(request: Request, user_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == int(user_id), Notification.is_read.is_(False))
        .order_by(Notification.created_at.desc())
        .all()
    )
    data = [
        {
            "id": int(r.id),
            "user_id": int(r.user_id),
            "type": str(r.type.value if hasattr(r.type, "value") else r.type),
            "title": r.title,
            "message": r.message,
            "data": r.data or {},
            "is_read": bool(r.is_read),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"request_id": request.state.request_id, "data": data, "error": None}


class MarkReadPayload(BaseModel):
    is_read: bool = True


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    request: Request,
    notification_id: int,
    payload: MarkReadPayload,
    db: Session = Depends(get_db),
):
    row = db.query(Notification).filter(Notification.id == int(notification_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")

    row.is_read = bool(payload.is_read)
    db.commit()
    db.refresh(row)

    data = {
        "id": int(row.id),
        "is_read": bool(row.is_read),
    }
    return {"request_id": request.state.request_id, "data": data, "error": None}
