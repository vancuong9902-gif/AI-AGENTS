from __future__ import annotations

from app.db.session import SessionLocal
from app.services.teacher_report_export_service import build_classroom_report_pdf


def task_export_teacher_report_pdf(classroom_id: int) -> dict:
    db = SessionLocal()
    try:
        path = build_classroom_report_pdf(classroom_id=int(classroom_id), db=db)
        return {"classroom_id": int(classroom_id), "pdf_path": path}
    finally:
        db.close()
