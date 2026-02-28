from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.learning_plan import (
    LearningPlan,
    LearningPlanTaskCompletion,
    LearningPlanHomeworkSubmission,
)
from app.services.homework_service import grade_homework


def save_teacher_plan(
    db: Session,
    *,
    user_id: int,
    teacher_id: int | None,
    classroom_id: int | None = None,
    assigned_topic: str | None,
    level: str,
    days_total: int,
    minutes_per_day: int,
    teacher_plan: Dict[str, Any],
) -> LearningPlan:
    row = LearningPlan(
        user_id=int(user_id),
        teacher_id=int(teacher_id) if teacher_id is not None else None,
        classroom_id=int(classroom_id) if classroom_id is not None else None,
        assigned_topic=(assigned_topic or None),
        level=str(level or "beginner"),
        days_total=int(days_total or 7),
        minutes_per_day=int(minutes_per_day or 35),
        plan_json=(teacher_plan or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_latest_plan(db: Session, *, user_id: int, classroom_id: int | None = None) -> Optional[Dict[str, Any]]:
    q = db.query(LearningPlan).filter(LearningPlan.user_id == int(user_id))
    if classroom_id is not None:
        q = q.filter(LearningPlan.classroom_id == int(classroom_id))

    row = q.order_by(LearningPlan.created_at.desc()).first()
    if not row:
        return None

    # Completion map
    completion_rows = (
        db.query(LearningPlanTaskCompletion)
        .filter(LearningPlanTaskCompletion.plan_id == int(row.id))
        .all()
    )
    comp: Dict[str, bool] = {}
    for c in completion_rows:
        comp[f"{int(c.day_index)}:{int(c.task_index)}"] = bool(c.completed)

    # Homework submissions map
    hw_rows = (
        db.query(LearningPlanHomeworkSubmission)
        .filter(
            LearningPlanHomeworkSubmission.plan_id == int(row.id),
            LearningPlanHomeworkSubmission.user_id == int(user_id),
        )
        .all()
    )
    hw: Dict[int, Dict[str, Any]] = {}
    for h in hw_rows:
        hw[int(h.day_index)] = {
            "answer_text": h.answer_text,
            "answer_json": (getattr(h, "answer_json", None) or {}),
            "grade": (h.grade_json or {}),
        }

    tp = row.plan_json or {}
    if isinstance(tp, dict):
        # Ensure the client can mutate persisted state via plan_id
        tp = {**tp, "plan_id": int(row.id)}

    return {
        "plan_id": int(row.id),
        "user_id": int(row.user_id),
        "teacher_id": int(row.teacher_id) if row.teacher_id is not None else None,
        "classroom_id": int(row.classroom_id) if getattr(row, "classroom_id", None) is not None else None,
        "assigned_topic": row.assigned_topic,
        "level": row.level,
        "days_total": int(row.days_total),
        "minutes_per_day": int(row.minutes_per_day),
        "teacher_plan": tp,
        "task_completion": comp,
        "homework_submissions": hw,
    }


def set_task_completion(
    db: Session,
    *,
    plan_id: int,
    day_index: int,
    task_index: int,
    completed: bool,
) -> Dict[str, Any]:
    row = (
        db.query(LearningPlanTaskCompletion)
        .filter(
            LearningPlanTaskCompletion.plan_id == int(plan_id),
            LearningPlanTaskCompletion.day_index == int(day_index),
            LearningPlanTaskCompletion.task_index == int(task_index),
        )
        .first()
    )
    if not row:
        row = LearningPlanTaskCompletion(
            plan_id=int(plan_id),
            day_index=int(day_index),
            task_index=int(task_index),
            completed=bool(completed),
        )
        db.add(row)
    else:
        row.completed = bool(completed)
    db.commit()
    return {"day_index": int(day_index), "task_index": int(task_index), "completed": bool(completed)}


def grade_homework_from_plan(
    db: Session,
    *,
    plan_id: int,
    user_id: int,
    day_index: int,
    answer_text: str,
    mcq_answers: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    plan = db.query(LearningPlan).filter(LearningPlan.id == int(plan_id)).first()
    if not plan:
        raise ValueError("Plan not found")

    teacher_plan = plan.plan_json or {}
    days = teacher_plan.get("days") if isinstance(teacher_plan, dict) else None
    if not isinstance(days, list):
        raise ValueError("Plan is invalid")

    day = next((d for d in days if int(d.get("day_index") or 0) == int(day_index)), None)
    if not isinstance(day, dict) or not isinstance(day.get("homework"), dict):
        raise ValueError("Homework not found for this day")

    hw = day.get("homework") or {}

    # -------------------------
    # 1) Grade MCQ (auto)
    # -------------------------
    mcq_qs = hw.get("mcq_questions") or []
    if isinstance(mcq_qs, dict):
        mcq_qs = [mcq_qs]
    if not isinstance(mcq_qs, list):
        mcq_qs = []

    ans_map: Dict[str, int] = {}
    if isinstance(mcq_answers, dict):
        for k, v in mcq_answers.items():
            try:
                ans_map[str(k)] = int(v)
            except Exception:
                continue

    mcq_breakdown: list[dict] = []
    mcq_score = 0
    mcq_max = 0

    for it in mcq_qs:
        if not isinstance(it, dict):
            continue
        qid = str(it.get("question_id") or "").strip()
        stem = str(it.get("stem") or "").strip()
        options = it.get("options") or []
        try:
            correct = int(it.get("correct_index"))
        except Exception:
            correct = -1
        try:
            mp = int(it.get("max_points") or 1)
        except Exception:
            mp = 1
        mp = max(1, min(10, mp))
        if not qid:
            # stable fallback id
            qid = f"mcq_{len(mcq_breakdown)+1}"

        chosen = ans_map.get(qid)
        is_correct = (chosen is not None) and (int(chosen) == int(correct))
        sp = int(mp if is_correct else 0)
        mcq_score += sp
        mcq_max += mp

        mcq_breakdown.append(
            {
                "type": "mcq",
                "question_id": qid,
                "stem": stem,
                "options": options,
                "chosen_index": int(chosen) if chosen is not None else None,
                "correct_index": int(correct) if correct is not None else None,
                "is_correct": bool(is_correct),
                "score_points": int(sp),
                "max_points": int(mp),
                "explanation": it.get("explanation") or None,
                "sources": it.get("sources") or [],
            }
        )

    # -------------------------
    # 2) Grade Essay (LLM/heuristic)
    # -------------------------
    essay_result = grade_homework(
        db,
        user_id=int(user_id),
        stem=str(hw.get("stem") or ""),
        answer_text=str(answer_text or ""),
        max_points=int(hw.get("max_points") or 10),
        rubric=hw.get("rubric") or [],
        sources=hw.get("sources") or [],
    )

    try:
        essay_score = int(essay_result.get("score_points", 0) or 0)
    except Exception:
        essay_score = 0
    try:
        essay_max = int(essay_result.get("max_points", 0) or 0)
    except Exception:
        essay_max = int(hw.get("max_points") or 10)

    total_score = int(mcq_score + essay_score)
    total_max = int(mcq_max + essay_max)

    # Top-level comment keeps backward compatibility but also shows MCQ split.
    essay_comment = str(essay_result.get("comment") or "").strip()
    comment_parts = []
    if mcq_qs:
        comment_parts.append(f"Trắc nghiệm: {mcq_score}/{mcq_max}đ")
    comment_parts.append(f"Tự luận: {essay_score}/{essay_max}đ")
    if essay_comment:
        comment_parts.append(essay_comment)

    result: Dict[str, Any] = {
        # Backward-compatible keys
        "score_points": int(total_score),
        "max_points": int(total_max),
        "comment": " • ".join([p for p in comment_parts if p]),
        "rubric_breakdown": essay_result.get("rubric_breakdown") or [],

        # Extra structured fields for UI
        "mcq_score_points": int(mcq_score),
        "mcq_max_points": int(mcq_max),
        "essay_score_points": int(essay_score),
        "essay_max_points": int(essay_max),
        "essay_comment": essay_comment or None,
        "mcq_breakdown": mcq_breakdown,
    }

    # Upsert submission
    sub = (
        db.query(LearningPlanHomeworkSubmission)
        .filter(
            LearningPlanHomeworkSubmission.plan_id == int(plan_id),
            LearningPlanHomeworkSubmission.user_id == int(user_id),
            LearningPlanHomeworkSubmission.day_index == int(day_index),
        )
        .first()
    )
    if not sub:
        sub = LearningPlanHomeworkSubmission(
            plan_id=int(plan_id),
            user_id=int(user_id),
            day_index=int(day_index),
            answer_text=str(answer_text or ""),
            answer_json={"mcq_answers": ans_map},
            grade_json=(result or {}),
        )
        db.add(sub)
    else:
        sub.answer_text = str(answer_text or "")
        sub.answer_json = {"mcq_answers": ans_map}
        sub.grade_json = (result or {})
    db.commit()

    return result


def get_homework_submission(
    db: Session,
    *,
    plan_id: int,
    user_id: int,
    day_index: int,
) -> Optional[Dict[str, Any]]:
    sub = (
        db.query(LearningPlanHomeworkSubmission)
        .filter(
            LearningPlanHomeworkSubmission.plan_id == int(plan_id),
            LearningPlanHomeworkSubmission.user_id == int(user_id),
            LearningPlanHomeworkSubmission.day_index == int(day_index),
        )
        .first()
    )
    if not sub:
        return None
    return {
        "day_index": int(sub.day_index),
        "answer_text": sub.answer_text,
        "answer_json": (getattr(sub, "answer_json", None) or {}),
        "grade": sub.grade_json or {},
    }
