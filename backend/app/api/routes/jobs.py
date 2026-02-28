from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.infra.queue import enqueue, is_async_enabled, fetch_job
from app.tasks.index_tasks import task_index_document, task_rebuild_vector_index
from app.tasks.drift_tasks import task_run_drift_check
from app.models.drift_report import DriftReport

router = APIRouter(tags=["jobs"])


@router.post("/jobs/index/document/{document_id}")
def enqueue_index_document(request: Request, document_id: int) -> Dict[str, Any]:
    res = enqueue(task_index_document, int(document_id), queue_name="index")
    return {"request_id": request.state.request_id, "data": res, "error": None}


@router.post("/jobs/index/rebuild")
def enqueue_rebuild_index(request: Request) -> Dict[str, Any]:
    res = enqueue(task_rebuild_vector_index, queue_name="index")
    return {"request_id": request.state.request_id, "data": res, "error": None}


@router.post("/jobs/drift/check")
def enqueue_drift_check(
    request: Request,
    days: int = 7,
    user_id: Optional[int] = None,
    document_id: Optional[int] = None,
) -> Dict[str, Any]:
    res = enqueue(task_run_drift_check, days=int(days), user_id=user_id, document_id=document_id, queue_name="monitor")
    return {"request_id": request.state.request_id, "data": res, "error": None}


@router.get("/jobs/status/{job_id}")
def job_status(request: Request, job_id: str) -> Dict[str, Any]:
    if not is_async_enabled():
        raise HTTPException(status_code=400, detail="Async queue disabled (no Redis/RQ or ASYNC_QUEUE_ENABLED=false)")
    job = fetch_job(str(job_id))
    data: Dict[str, Any] = {
        "job_id": str(job.id),
        "status": str(job.get_status()),
        "enqueued_at": str(job.enqueued_at) if job.enqueued_at else None,
        "started_at": str(job.started_at) if job.started_at else None,
        "ended_at": str(job.ended_at) if job.ended_at else None,
        "exc_info": job.exc_info if job.is_failed else None,
    }
    if job.is_finished:
        data["result"] = job.result
    return {"request_id": request.state.request_id, "data": data, "error": None}


@router.get("/jobs/drift/reports")
def list_drift_reports(
    request: Request,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    rows = (
        db.query(DriftReport)
        .order_by(DriftReport.id.desc())
        .limit(int(max(1, min(200, limit))))
        .all()
    )
    out = []
    for r in rows:
        out.append(
            {
                "id": int(r.id),
                "scope": r.scope,
                "user_id": r.user_id,
                "document_id": r.document_id,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
                "overall": (r.report_json or {}).get("overall"),
            }
        )
    return {"request_id": request.state.request_id, "data": {"reports": out}, "error": None}


@router.get("/jobs/drift/reports/{report_id}")
def read_drift_report(
    request: Request,
    report_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    row = db.query(DriftReport).filter(DriftReport.id == int(report_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Drift report not found")
    return {
        "request_id": request.state.request_id,
        "data": {
            "id": int(row.id),
            "scope": row.scope,
            "user_id": row.user_id,
            "document_id": row.document_id,
            "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
            "report": row.report_json or {},
        },
        "error": None,
    }
