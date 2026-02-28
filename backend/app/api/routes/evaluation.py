from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.attempt import Attempt
from app.models.classroom_assessment import ClassroomAssessment
from app.models.diagnostic_attempt import DiagnosticAttempt
from app.models.quiz_set import QuizSet
from app.models.user import User

router = APIRouter(tags=["evaluation"])


def _split_attempt_scores(attempt: Attempt) -> dict:
    """Best-effort split score from Attempt.breakdown_json.

    - mcq_percent: based on is_correct
    - essay_percent: based on score_points/max_points when graded
    - total_percent: 70/30 if there is any essay graded, else mcq_percent
    - pending: essay exists but not graded
    """

    breakdown = list(attempt.breakdown_json or [])
    mcq_earned = mcq_total = 0
    essay_earned = essay_total = 0
    pending = False

    for it in breakdown:
        t = (it.get("type") or "").lower()
        if t == "mcq":
            mcq_total += 1
            if bool(it.get("is_correct")):
                mcq_earned += 1
        elif t == "essay":
            # if essay exists but not graded yet
            if not bool(it.get("graded")):
                pending = True
                continue
            mp = int(it.get("max_points", 0) or 0)
            sp = int(it.get("score_points", 0) or 0)
            if mp > 0:
                essay_total += mp
                essay_earned += max(0, min(sp, mp))

    mcq_percent = int(round((mcq_earned / mcq_total) * 100)) if mcq_total else 0
    essay_percent = int(round((essay_earned / essay_total) * 100)) if essay_total else 0

    if essay_total > 0:
        total_percent = int(round(0.7 * mcq_percent + 0.3 * essay_percent))
    else:
        # essay not graded yet (or no essay) => show mcq
        total_percent = mcq_percent

    # Fallback: if breakdown is empty, use attempt.score_percent
    if not breakdown:
        total_percent = int(attempt.score_percent or 0)

    return {
        "mcq_percent": mcq_percent,
        "essay_percent": essay_percent,
        "total_percent": total_percent,
        "pending": pending,
    }


def _topic_mastery_from_attempt(attempt: Attempt) -> dict[str, float]:
    """Compute mastery_by_topic (0..1) from attempt.breakdown_json."""
    breakdown = list(attempt.breakdown_json or [])
    earned: dict[str, float] = {}
    total: dict[str, float] = {}

    for it in breakdown:
        topic = (it.get("topic") or "tài liệu").strip().lower() or "tài liệu"
        mp = float(it.get("max_points", 1) or 1)
        sp = float(it.get("score_points", 0) or 0)
        # MCQ uses max_points=1; essay uses rubric points.
        total[topic] = total.get(topic, 0.0) + mp
        earned[topic] = earned.get(topic, 0.0) + max(0.0, min(sp, mp))

    out: dict[str, float] = {}
    for t, tp in total.items():
        out[t] = round((earned.get(t, 0.0) / tp), 4) if tp else 0.0
    return out


def _level_from_percent(score_percent: int | None) -> str | None:
    if score_percent is None:
        return None
    s = int(score_percent)
    if s < 40:
        return "beginner"
    if s <= 70:
        return "intermediate"
    return "advanced"


def _attempt_to_stage_payload(*, attempt: Attempt, stage: str) -> dict:
    split = _split_attempt_scores(attempt)
    total = int(split["total_percent"])
    return {
        "attempt_id": int(attempt.id),
        "assessment_id": int(attempt.quiz_set_id),
        "score_percent": total,
        "mcq_score_percent": int(split["mcq_percent"]),
        "essay_score_percent": int(split["essay_percent"]),
        "pending": bool(split["pending"]),
        "level": _level_from_percent(total),
        "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
        "mastery": {"by_topic": _topic_mastery_from_attempt(attempt)},
        "stage": stage,
    }


def _diag_to_stage_payload(*, diag: DiagnosticAttempt, stage: str) -> dict:
    return {
        "attempt_id": int(diag.attempt_id) if diag.attempt_id is not None else int(diag.id),
        "assessment_id": int(diag.assessment_id) if diag.assessment_id is not None else None,
        "score_percent": int(diag.score_percent),
        "mcq_score_percent": int(diag.mcq_score_percent),
        "essay_score_percent": int(diag.essay_score_percent),
        "pending": False,
        "level": diag.level,
        "created_at": diag.created_at.isoformat() if diag.created_at else None,
        "mastery": (diag.mastery_json or {}),
        "stage": stage,
    }


def _by_topic(mastery: dict | None) -> dict[str, float]:
    if not isinstance(mastery, dict):
        return {}
    by = mastery.get("by_topic")
    if not isinstance(by, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in by.items():
        try:
            out[str(k)] = float(v)
        except Exception:
            continue
    return out


def _latest_attempt(
    db: Session,
    *,
    user_id: int,
    assessment_ids: list[int] | None,
    kinds: list[str],
) -> Attempt | None:
    q = (
        db.query(Attempt)
        .join(QuizSet, Attempt.quiz_set_id == QuizSet.id)
        .filter(Attempt.user_id == int(user_id))
        .filter(QuizSet.kind.in_(kinds))
    )
    if assessment_ids is not None:
        q = q.filter(Attempt.quiz_set_id.in_([int(x) for x in assessment_ids]))
    return q.order_by(Attempt.created_at.desc()).first()


@router.get("/evaluation/{user_id}/overall")
def overall_progress(
    request: Request,
    user_id: int,
    classroom_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Tổng hợp tiến bộ.

    Default (no classroom_id): backward-compatible.
      - Pre-test: DiagnosticAttempt.stage='pre' (fallback: latest Attempt kind='diagnostic_pre')
      - Giữa khóa: latest Attempt kind in {'midterm','assessment'}
      - Cuối khóa: DiagnosticAttempt.stage='post' (fallback: latest Attempt kind='diagnostic_post')

    When classroom_id is provided: compute strictly within that classroom.
      - Use Attempt records for quiz_sets mapped via classroom_assessments.

    Điểm tổng kết (POST trên dashboard) = 50% giữa khóa + 50% cuối khóa.
    """

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    assessment_ids: list[int] | None = None
    if classroom_id is not None:
        assessment_ids = [
            int(r[0])
            for r in (
                db.query(ClassroomAssessment.assessment_id)
                .filter(ClassroomAssessment.classroom_id == int(classroom_id))
                .all()
            )
        ]
        if not assessment_ids:
            raise HTTPException(status_code=404, detail="No assessments for this classroom")

    # ---- Collect attempts / diagnostics
    pre_payload = None
    post_payload = None

    if classroom_id is None:
        pre_diag = (
            db.query(DiagnosticAttempt)
            .filter(DiagnosticAttempt.user_id == int(user_id), DiagnosticAttempt.stage == "pre")
            .order_by(DiagnosticAttempt.created_at.desc())
            .first()
        )
        post_diag = (
            db.query(DiagnosticAttempt)
            .filter(DiagnosticAttempt.user_id == int(user_id), DiagnosticAttempt.stage == "post")
            .order_by(DiagnosticAttempt.created_at.desc())
            .first()
        )

        if pre_diag:
            pre_payload = _diag_to_stage_payload(diag=pre_diag, stage="pre")
        else:
            pre_attempt = _latest_attempt(db, user_id=int(user_id), assessment_ids=None, kinds=["diagnostic_pre"])
            if pre_attempt:
                pre_payload = _attempt_to_stage_payload(attempt=pre_attempt, stage="pre")

        if post_diag:
            post_payload = _diag_to_stage_payload(diag=post_diag, stage="post")
        else:
            post_attempt = _latest_attempt(db, user_id=int(user_id), assessment_ids=None, kinds=["diagnostic_post"])
            if post_attempt:
                post_payload = _attempt_to_stage_payload(attempt=post_attempt, stage="post")
    else:
        pre_attempt = _latest_attempt(db, user_id=int(user_id), assessment_ids=assessment_ids, kinds=["diagnostic_pre"])
        if pre_attempt:
            pre_payload = _attempt_to_stage_payload(attempt=pre_attempt, stage="pre")

        post_attempt = _latest_attempt(db, user_id=int(user_id), assessment_ids=assessment_ids, kinds=["diagnostic_post"])
        if post_attempt:
            post_payload = _attempt_to_stage_payload(attempt=post_attempt, stage="post")

    # Midterm (in-course)
    mid_attempt = _latest_attempt(
        db,
        user_id=int(user_id),
        assessment_ids=assessment_ids,
        kinds=["midterm", "assessment"],
    )

    mid_payload = None
    mid_pending = False
    if mid_attempt:
        mid_payload = _attempt_to_stage_payload(attempt=mid_attempt, stage="midterm")
        mid_pending = bool(mid_payload.get("pending"))

    if not pre_payload and not post_payload and not mid_payload:
        raise HTTPException(status_code=404, detail="No attempts found")

    pre_score = int(pre_payload["score_percent"]) if pre_payload else None
    final_score = int(post_payload["score_percent"]) if post_payload else None

    pre_mcq = int(pre_payload["mcq_score_percent"]) if pre_payload else None
    pre_essay = int(pre_payload["essay_score_percent"]) if pre_payload else None
    final_mcq = int(post_payload["mcq_score_percent"]) if post_payload else None
    final_essay = int(post_payload["essay_score_percent"]) if post_payload else None

    # Weighted POST = 50/50 (midterm + final)
    overall = None
    overall_mcq = None
    overall_essay = None
    overall_level = None

    if mid_payload and not mid_pending and (final_score is not None):
        overall = int(round(0.5 * float(mid_payload["score_percent"]) + 0.5 * float(final_score)))
        if mid_payload.get("mcq_score_percent") is not None and final_mcq is not None:
            overall_mcq = int(round(0.5 * float(mid_payload["mcq_score_percent"]) + 0.5 * float(final_mcq)))
        if mid_payload.get("essay_score_percent") is not None and final_essay is not None:
            overall_essay = int(round(0.5 * float(mid_payload["essay_score_percent"]) + 0.5 * float(final_essay)))
        overall_level = _level_from_percent(overall)

    # progress_rate: (overall - pre)/(100-pre)
    progress_rate = None
    if pre_score is not None and overall is not None:
        den = max(1e-9, 100.0 - float(pre_score))
        progress_rate = float(overall - pre_score) / den * 100.0
        progress_rate = max(0.0, min(100.0, float(progress_rate)))

    label = None
    if progress_rate is not None:
        label = "Có tiến bộ" if float(progress_rate) > 50.0 else "Cần cố gắng thêm"

    # Deltas: prefer overall when available
    delta_total = None
    if pre_score is not None:
        if overall is not None:
            delta_total = overall - pre_score
        elif final_score is not None:
            delta_total = final_score - pre_score

    delta_mcq = None
    if pre_mcq is not None:
        if overall_mcq is not None:
            delta_mcq = overall_mcq - pre_mcq
        elif final_mcq is not None:
            delta_mcq = final_mcq - pre_mcq

    delta_essay = None
    if pre_essay is not None:
        if overall_essay is not None:
            delta_essay = overall_essay - pre_essay
        elif final_essay is not None:
            delta_essay = final_essay - pre_essay

    # Topic-level gains (if pre/post have by_topic mastery)
    topic_gain = None
    pre_by = _by_topic(pre_payload.get("mastery") if pre_payload else None)
    post_by = _by_topic(post_payload.get("mastery") if post_payload else None)
    if pre_by and post_by:
        all_topics = sorted(set(pre_by.keys()) | set(post_by.keys()))
        gains = []
        for t in all_topics:
            a = float(pre_by.get(t, 0.0))
            b = float(post_by.get(t, 0.0))
            gains.append({"topic": t, "pre_mastery": round(a, 4), "post_mastery": round(b, 4), "delta": round(b - a, 4)})
        gains.sort(key=lambda x: float(x.get("delta", 0.0)), reverse=True)
        topic_gain = gains[:8]

    # Message
    if mid_payload and mid_pending:
        msg = "Bài giữa khóa có câu tự luận chưa chấm. Hãy chấm bài giữa khóa để tính điểm tổng kết (50% + 50%)."
    elif overall is None:
        msg = "Chưa đủ dữ liệu để tính điểm tổng kết (cần cả giữa khóa và cuối khóa)."
    else:
        pr = None if progress_rate is None else round(float(progress_rate), 1)
        msg = f"Điểm tổng kết: {overall}%. Progress rate: {pr}% → {label}."

    data = {
        "user_id": int(user_id),
        "classroom_id": int(classroom_id) if classroom_id is not None else None,
        "pre": pre_payload,
        "post": post_payload,
        "midterm": mid_payload,
        "post_weighted": {
            "score_percent": overall,
            "mcq_score_percent": overall_mcq,
            "essay_score_percent": overall_essay,
            "level": overall_level,
            "pending": bool(mid_pending) if mid_payload else None,
            "formula": "0.5*midterm + 0.5*final",
            "components": {
                "midterm_percent": mid_payload["score_percent"] if mid_payload else None,
                "final_percent": final_score,
            },
        },
        "overall_percent": overall,
        "overall_mcq_percent": overall_mcq,
        "overall_essay_percent": overall_essay,
        "overall_level": overall_level,
        "progress_rate": progress_rate,
        "assessment_label": label,
        "delta_score": delta_total,
        "delta_mcq": delta_mcq,
        "delta_essay": delta_essay,
        "topic_gain": topic_gain,
        "message": msg,
    }

    return {"request_id": request.state.request_id, "data": data, "error": None}
