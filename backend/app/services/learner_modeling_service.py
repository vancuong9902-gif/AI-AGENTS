from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.document_topic import DocumentTopic


# ==========================================================
# Learner Modeling Service (research prototype)
#
# Maintain a lightweight, data-efficient learner model under:
#  - limited labeled data
#  - noisy assessment signals
#  - heterogeneous PDFs/domains
#
# We implement an interpretable Bayesian update per topic using a Beta model:
#   mastery ~ Beta(alpha, beta)
# Observations are fractional correctness y in [0,1]. Update:
#   alpha <- alpha + y
#   beta  <- beta  + (1-y)
# Posterior mean mastery = alpha / (alpha + beta)
#
# This behaves like a smoothed knowledge tracing signal while remaining stable.
# ==========================================================


def _now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _topic_for_chunk_index(db: Session, *, document_id: int, chunk_index: int) -> Optional[DocumentTopic]:
    return (
        db.query(DocumentTopic)
        .filter(DocumentTopic.document_id == int(document_id))
        .filter(DocumentTopic.start_chunk_index <= int(chunk_index))
        .filter(DocumentTopic.end_chunk_index >= int(chunk_index))
        .order_by(DocumentTopic.topic_index.asc())
        .first()
    )


def infer_topics_from_sources(db: Session, *, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Infer document topics touched by a question's evidence sources.

    Returns:
      [{document_id, topic_id, topic_title, topic_index}, ...]
    """

    chunk_ids: List[int] = []
    for s in sources or []:
        try:
            cid = int((s or {}).get("chunk_id"))
            chunk_ids.append(cid)
        except Exception:
            continue
    chunk_ids = list(dict.fromkeys(chunk_ids))[:6]
    if not chunk_ids:
        return []

    chunks = (
        db.query(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.chunk_index)
        .filter(DocumentChunk.id.in_(chunk_ids))
        .all()
    )

    seen: set[Tuple[int, int]] = set()
    out: List[Dict[str, Any]] = []
    for _cid, doc_id, ch_idx in chunks:
        topic = _topic_for_chunk_index(db, document_id=int(doc_id), chunk_index=int(ch_idx))
        if not topic:
            continue
        key = (int(doc_id), int(topic.id))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "document_id": int(doc_id),
                "topic_id": int(topic.id),
                "topic_title": str(topic.title or ""),
                "topic_index": int(topic.topic_index or 0),
            }
        )
    return out


def beta_update_topic_stats(
    mastery_json: Dict[str, Any],
    *,
    topic_key: str,
    y: float,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
) -> Dict[str, Any]:
    """Update per-topic Beta posterior using fractional correctness y in [0,1]."""

    y = _clip01(float(y))

    stats = mastery_json.setdefault("topic_stats", {})
    if not isinstance(stats, dict):
        mastery_json["topic_stats"] = {}
        stats = mastery_json["topic_stats"]

    rec = stats.get(topic_key) if isinstance(stats.get(topic_key), dict) else {}
    a = _safe_float(rec.get("alpha"), prior_alpha)
    b = _safe_float(rec.get("beta"), prior_beta)
    n = int(_safe_float(rec.get("n"), 0))

    a = float(a) + float(y)
    b = float(b) + float(1.0 - float(y))
    n += 1

    mean = float(a) / float(max(1e-9, a + b))

    rec_out = {
        "alpha": round(float(a), 4),
        "beta": round(float(b), 4),
        "n": int(n),
        "mean": round(mean, 4),
        "updated_at": _now_iso(),
    }
    stats[topic_key] = rec_out

    # Mirror a simplified mastery map for fast policy access.
    tm = mastery_json.setdefault("topic_mastery", {})
    if not isinstance(tm, dict):
        mastery_json["topic_mastery"] = {}
        tm = mastery_json["topic_mastery"]
    tm[topic_key] = round(mean, 4)

    return mastery_json


def update_mastery_from_breakdown(
    db: Session,
    *,
    mastery_json: Dict[str, Any],
    breakdown: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Update mastery_json using attempt breakdown + sources -> topic mapping.

    - Each question contributes fractional correctness y = score_points / max_points.
    - The update is applied to each inferred topic touched by the question's sources.
      (If a question cites 2 topics, both receive the update; conservative approximation.)
    """

    mj = dict(mastery_json or {})

    for b in breakdown or []:
        try:
            mp = float(b.get("max_points", 1.0) or 1.0)
            sp = float(b.get("score_points", 0.0) or 0.0)
            y = sp / float(max(1e-9, mp))
        except Exception:
            y = 0.0
        y = _clip01(y)

        sources = b.get("sources") if isinstance(b.get("sources"), list) else []
        topics = infer_topics_from_sources(db, sources=sources)
        if not topics:
            mj = beta_update_topic_stats(mj, topic_key="__global__", y=y)
            continue

        for t in topics:
            # Stable key: doc + topic id, with title for human debugging.
            key = f"doc{t['document_id']}:topic{t['topic_id']}:{t['topic_title']}".strip(":")
            mj = beta_update_topic_stats(mj, topic_key=key, y=y)

    return mj
