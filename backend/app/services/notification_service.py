from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.classroom import Classroom, ClassroomMember
from app.models.notification import Notification, NotificationType
from app.models.user import User

logger = logging.getLogger(__name__)

# In-memory notification store for lightweight teacher polling.
_notifications: list[dict[str, Any]] = []


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


def push_notification(*, teacher_id: int, message: str, payload: dict | None = None) -> dict[str, Any]:
    notif = {
        "id": len(_notifications) + 1,
        "teacher_id": int(teacher_id),
        "message": str(message),
        "payload": payload or {},
        "read": False,
    }
    _notifications.append(notif)
    logger.info("[NOTIFY] teacher_id=%s: %s", teacher_id, message)
    return notif


def get_notifications_for_teacher(teacher_id: int) -> list[dict[str, Any]]:
    return [n for n in _notifications if int(n.get("teacher_id") or 0) == int(teacher_id) and not bool(n.get("read"))]


def mark_read(notification_id: int) -> bool:
    for notif in _notifications:
        if int(notif.get("id") or 0) == int(notification_id):
            notif["read"] = True
            return True
    return False


def notify_teacher_student_finished(
    db: Session,
    *,
    student_id: int,
    classroom_id: int,
    exam_kind: str,
    score_percent: float,
    classification: str,
) -> None:
    try:
        student = db.query(User).filter(User.id == int(student_id)).first()
        student_name = getattr(student, "name", None) or getattr(student, "email", f"ID {student_id}")

        classroom = db.query(Classroom).filter(Classroom.id == int(classroom_id)).first()
        classroom_name = getattr(classroom, "name", f"Lớp {classroom_id}") if classroom else f"Lớp {classroom_id}"

        teachers = (
            db.query(ClassroomMember)
            .filter(
                ClassroomMember.classroom_id == int(classroom_id),
                ClassroomMember.role == "teacher",
            )
            .all()
        )

        exam_label = "Bài Kiểm Tra Cuối Kỳ" if exam_kind == "diagnostic_post" else "Bài Kiểm Tra Đầu Vào"
        level_label = {"gioi": "Giỏi", "kha": "Khá", "trung_binh": "Trung Bình", "yeu": "Yếu"}.get(classification, classification)

        message = (
            f"📋 {student_name} vừa hoàn thành {exam_label} "
            f"tại {classroom_name}. "
            f"Điểm: {score_percent:.1f}% – Xếp loại: {level_label}."
        )

        for teacher_member in teachers:
            push_notification(
                teacher_id=int(teacher_member.user_id),
                message=message,
                payload={
                    "student_id": int(student_id),
                    "classroom_id": int(classroom_id),
                    "exam_kind": str(exam_kind),
                    "score_percent": float(score_percent),
                    "classification": str(classification),
                },
            )
    except Exception as e:
        logger.warning("notify_teacher_student_finished failed: %s", e)
