from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType


def create_notification(
    db: Session,
    *,
    user_id: int,
    type: str,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> Notification:
    notif_type = NotificationType(type)
    row = Notification(
        user_id=int(user_id),
        type=notif_type,
        title=str(title),
        message=str(message),
        data=data or {},
        is_read=False,
    )
    db.add(row)
    db.flush()
    return row
