from __future__ import annotations

from typing import Any, Dict, Optional

from app.db.session import SessionLocal
from app.services.drift_monitoring_service import compute_drift_report, store_drift_report


def task_run_drift_check(*, days: int = 7, user_id: Optional[int] = None, document_id: Optional[int] = None) -> Dict[str, Any]:
    """Background drift monitoring.

    Produces a DriftReport row for audit/dashboard use.
    """
    db = SessionLocal()
    try:
        report = compute_drift_report(db, days=int(days), user_id=user_id, document_id=document_id)
        row = store_drift_report(db, report, user_id=user_id, document_id=document_id)
        return {"stored": True, "drift_report_id": int(row.id), "overall": report.get("overall")}
    finally:
        db.close()
