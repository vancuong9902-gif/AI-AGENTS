from __future__ import annotations

import datetime as _dt
import math
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.rag_query import RAGQuery
from app.models.document_chunk import DocumentChunk
from app.models.policy_decision_log import PolicyDecisionLog
from app.models.drift_report import DriftReport
from app.models.learner_profile import LearnerProfile


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, float(x))))


def _entropy(counts: Dict[str, int]) -> float:
    total = float(sum(max(0, int(v)) for v in counts.values()))
    if total <= 0:
        return 0.0
    h = 0.0
    for v in counts.values():
        p = float(max(0, int(v))) / total
        if p > 1e-12:
            h -= p * math.log(p)
    # normalize by log(|A|)
    k = max(2, len([v for v in counts.values() if v > 0]))
    return float(h / math.log(k))


def _window(db: Session, model, start: _dt.datetime, end: _dt.datetime):
    return db.query(model).filter(model.created_at >= start).filter(model.created_at < end)


def compute_retrieval_drift(db: Session, *, days: int = 7) -> Dict[str, Any]:
    now = _utcnow()
    w = _dt.timedelta(days=int(days))
    cur_start, cur_end = now - w, now
    prev_start, prev_end = now - 2 * w, now - w

    cur = _window(db, RAGQuery, cur_start, cur_end).all()
    prev = _window(db, RAGQuery, prev_start, prev_end).all()

    def _stats(rows: List[RAGQuery]) -> Dict[str, float]:
        if not rows:
            return {"n": 0, "empty_rate": 0.0, "avg_hits": 0.0, "avg_doc_diversity": 0.0}
        empty = 0
        hits = []
        all_chunk_ids: List[int] = []
        per_query_chunk_ids: List[List[int]] = []
        for r in rows:
            ids = list(r.result_chunk_ids or [])
            per_query_chunk_ids.append(ids)
            all_chunk_ids.extend(ids)
            if not ids:
                empty += 1
            hits.append(len(ids))

        # doc diversity proxy: distinct doc_ids among returned chunks per query
        doc_map: Dict[int, int] = {}
        if all_chunk_ids:
            uniq = list(set(int(x) for x in all_chunk_ids if isinstance(x, int) or str(x).isdigit()))
            for chunk in db.query(DocumentChunk).filter(DocumentChunk.id.in_(uniq)).all():
                doc_map[int(chunk.id)] = int(chunk.document_id)

        diversities = []
        for ids in per_query_chunk_ids:
            docs = {doc_map.get(int(cid)) for cid in ids if int(cid) in doc_map}
            docs = {d for d in docs if d is not None}
            diversities.append(float(len(docs)))
        return {
            "n": float(len(rows)),
            "empty_rate": float(empty) / max(1.0, float(len(rows))),
            "avg_hits": float(sum(hits)) / max(1.0, float(len(hits))),
            "avg_doc_diversity": float(sum(diversities)) / max(1.0, float(len(diversities))),
        }

    s_cur = _stats(cur)
    s_prev = _stats(prev)

    drift = (
        abs(s_cur["empty_rate"] - s_prev["empty_rate"])
        + abs(s_cur["avg_hits"] - s_prev["avg_hits"]) / max(1.0, s_prev["avg_hits"] + 1e-6)
        + abs(s_cur["avg_doc_diversity"] - s_prev["avg_doc_diversity"]) / max(1.0, s_prev["avg_doc_diversity"] + 1e-6)
    )
    return {"window_days": int(days), "current": s_cur, "previous": s_prev, "drift_score": float(_clip(drift, 0.0, 3.0))}


def compute_policy_drift(db: Session, *, days: int = 7, user_id: Optional[int] = None) -> Dict[str, Any]:
    now = _utcnow()
    w = _dt.timedelta(days=int(days))
    cur_start, cur_end = now - w, now
    prev_start, prev_end = now - 2 * w, now - w

    qcur = _window(db, PolicyDecisionLog, cur_start, cur_end)
    qprev = _window(db, PolicyDecisionLog, prev_start, prev_end)
    if user_id is not None:
        qcur = qcur.filter(PolicyDecisionLog.user_id == int(user_id))
        qprev = qprev.filter(PolicyDecisionLog.user_id == int(user_id))

    cur = qcur.all()
    prev = qprev.all()

    def _stats(rows: List[PolicyDecisionLog]) -> Dict[str, float]:
        if not rows:
            return {"n": 0.0, "entropy": 0.0, "oscillation_rate": 0.0}
        counts: Dict[str, int] = {}
        actions = []
        for r in rows:
            a = str(r.action or "")
            actions.append(a)
            counts[a] = counts.get(a, 0) + 1
        ent = _entropy(counts)

        # oscillation proxy: consecutive inc/dec difficulty toggles
        osc = 0
        total_pairs = 0
        for a1, a2 in zip(actions[:-1], actions[1:]):
            total_pairs += 1
            if ("increase" in a1 and "decrease" in a2) or ("decrease" in a1 and "increase" in a2):
                osc += 1
        osc_rate = float(osc) / max(1.0, float(total_pairs))
        return {"n": float(len(rows)), "entropy": float(ent), "oscillation_rate": float(osc_rate)}

    s_cur = _stats(cur)
    s_prev = _stats(prev)
    drift = abs(s_cur["entropy"] - s_prev["entropy"]) + abs(s_cur["oscillation_rate"] - s_prev["oscillation_rate"])
    return {"window_days": int(days), "current": s_cur, "previous": s_prev, "drift_score": float(_clip(drift, 0.0, 2.0))}


def compute_learning_drift(db: Session, *, user_id: Optional[int] = None, document_id: Optional[int] = None) -> Dict[str, Any]:
    # Use analytics_history stored in LearnerProfile.mastery_json.
    # Drift: slope drops or becomes negative; dropout risk increases.
    now = _utcnow()

    q = db.query(LearnerProfile)
    if user_id is not None:
        q = q.filter(LearnerProfile.user_id == int(user_id))
    profiles = q.all()

    def _parse_ts(ts: Any) -> Optional[_dt.datetime]:
        try:
            return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            return None

    slopes = []
    risk_deltas = []
    for p in profiles:
        mj = p.mastery_json or {}
        hist = mj.get("analytics_history") if isinstance(mj.get("analytics_history"), list) else []
        # filter by document if stored (we store document_id optional)
        series = []
        for it in hist:
            if not isinstance(it, dict):
                continue
            if document_id is not None and int(it.get("document_id") or 0) != int(document_id):
                continue
            ts = _parse_ts(it.get("ts"))
            if not ts:
                continue
            series.append((ts, float(it.get("knowledge") or 0.0), float(it.get("dropout_risk") or 0.0)))
        if len(series) < 3:
            continue
        series.sort(key=lambda x: x[0])
        # compute 7-day slope approx (last minus first within 7 days)
        end_ts = series[-1][0]
        start_ts = end_ts - _dt.timedelta(days=7)
        win = [x for x in series if x[0] >= start_ts]
        if len(win) >= 2:
            dt_days = max(1e-6, (win[-1][0] - win[0][0]).total_seconds() / 86400.0)
            slope = (win[-1][1] - win[0][1]) / dt_days
            slopes.append(slope)
            risk_deltas.append(win[-1][2] - win[0][2])

    if not slopes:
        return {"window_days": 7, "avg_knowledge_slope": 0.0, "avg_dropout_risk_delta": 0.0, "drift_score": 0.0}

    avg_slope = float(sum(slopes)) / float(len(slopes))
    avg_risk_delta = float(sum(risk_deltas)) / float(len(risk_deltas))

    # Negative slope or rising risk => drift
    drift = _clip(-avg_slope * 10.0, 0.0, 2.0) + _clip(avg_risk_delta * 2.0, 0.0, 2.0)
    return {
        "window_days": 7,
        "avg_knowledge_slope": float(avg_slope),
        "avg_dropout_risk_delta": float(avg_risk_delta),
        "drift_score": float(drift),
    }


def compute_drift_report(db: Session, *, days: int = 7, user_id: Optional[int] = None, document_id: Optional[int] = None) -> Dict[str, Any]:
    now = _utcnow()
    r = compute_retrieval_drift(db, days=days)
    p = compute_policy_drift(db, days=days, user_id=user_id)
    l = compute_learning_drift(db, user_id=user_id, document_id=document_id)

    total = float(_clip(0.4 * r["drift_score"] + 0.3 * p["drift_score"] + 0.3 * l["drift_score"], 0.0, 2.0))
    level = "OK"
    if total >= 1.2:
        level = "ALERT"
    elif total >= 0.7:
        level = "WARN"

    return {
        "ts": now.isoformat(),
        "days": int(days),
        "scope": "user" if user_id is not None else "global",
        "user_id": user_id,
        "document_id": document_id,
        "retrieval": r,
        "policy": p,
        "learning": l,
        "overall": {"drift_score": total, "level": level},
    }


def store_drift_report(db: Session, report: Dict[str, Any], *, user_id: Optional[int] = None, document_id: Optional[int] = None) -> DriftReport:
    scope = "user" if user_id is not None else "global"
    row = DriftReport(scope=scope, user_id=user_id, document_id=document_id, report_json=report)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
