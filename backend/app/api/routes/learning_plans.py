from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.learning_plan import LearningPlan
from app.models.learner_profile import LearnerProfile
from app.schemas.learning_plans import (
    HomeworkGradeFromPlanRequest,
    LearningPlanLatestResponse,
    TaskCompleteRequest,
)
from app.services.learning_plan_storage_service import (
    get_latest_plan,
    get_homework_submission,
    grade_homework_from_plan,
    set_task_completion,
)


router = APIRouter(tags=["learning_plans"])


def _normalize_level(level: str | None) -> str:
    lv = str(level or "").lower()
    if "gioi" in lv:
        return "gioi"
    if "kha" in lv:
        return "kha"
    if "yeu" in lv:
        return "yeu"
    return "trung_binh"


@router.get("/learning-plans/{userId}/current")
def learning_plan_current(request: Request, userId: int, db: Session = Depends(get_db), classroom_id: int | None = None):
    latest = get_latest_plan(db, user_id=int(userId), classroom_id=classroom_id)
    if not latest:
        raise HTTPException(status_code=404, detail="No learning plan found")

    tp = latest.get("teacher_plan") or {}
    days = tp.get("days") if isinstance(tp, dict) else []
    if not isinstance(days, list):
        days = []

    level = _normalize_level(latest.get("level"))
    weak_topics: list[str] = []
    strong_topics: list[str] = []

    # Ưu tiên lấy từ plan_json kiểu LMS (assigned_tasks), fallback sang learner_profile.
    lp_row = db.query(LearningPlan).filter(LearningPlan.id == int(latest["plan_id"])).first()
    assigned_tasks = (lp_row.plan_json or {}).get("assigned_tasks", []) if lp_row and isinstance(lp_row.plan_json, dict) else []
    if isinstance(assigned_tasks, list) and assigned_tasks:
        for task in assigned_tasks:
            if not isinstance(task, dict):
                continue
            title = str(task.get("topic_title") or task.get("topic") or "").strip()
            reason = str(task.get("reason") or "").lower()
            if not title:
                continue
            if "nền tảng" in reason or "yếu" in reason:
                weak_topics.append(title)
            else:
                strong_topics.append(title)
    else:
        profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(userId)).first()
        mastery = getattr(profile, "mastery_json", {}) if profile else {}
        if isinstance(mastery, dict):
            for k, v in mastery.items():
                try:
                    score = float(v)
                except Exception:
                    continue
                if score < 60:
                    weak_topics.append(str(k))
                elif score >= 80:
                    strong_topics.append(str(k))

    items = []
    order = 1
    for d in sorted(days, key=lambda x: int(x.get("day_index", 0))):
        day_index = int(d.get("day_index") or 0)
        title = str(d.get("title") or f"Day {day_index}")
        for idx, task in enumerate(d.get("tasks") or []):
            ttype = str(task.get("type") or "study_material")
            item_type = "study_material"
            if ttype == "homework":
                item_type = "homework"
            elif ttype in {"quiz", "assessment"}:
                item_type = "quiz"

            topic_hint = title.replace("Ngày", "").strip() or title
            items.append(
                {
                    "type": item_type,
                    "topic_id": day_index,
                    "topic_title": topic_hint,
                    "content_ref": f"day:{day_index}:task:{idx}",
                    "difficulty": "medium" if level in {"kha", "trung_binh"} else ("hard" if level == "gioi" else "easy"),
                    "estimated_minutes": int(task.get("estimated_minutes") or 15),
                    "order": order,
                    "reason": str(task.get("instructions") or "AI gợi ý theo năng lực hiện tại của bạn."),
                    "status": "hoan_thanh" if latest.get("task_completion", {}).get(f"{day_index}:{idx}") else "chua_lam",
                    "day": day_index,
                }
            )
            order += 1

    completed = len([x for x in items if x.get("status") == "hoan_thanh"])

    total_minutes = sum(int(it.get("estimated_minutes") or 15) for it in items)
    estimated_days = max(1, (total_minutes + 44) // 45)
    ai_expl = (
        "Dựa trên kết quả bài kiểm tra và tiến độ hiện tại, AI đã tạo lộ trình học cá nhân hoá "
        "theo mức độ của bạn, ưu tiên các chủ đề yếu và giữ nhịp ôn tập phù hợp."
    )

    payload = {
        "plan_id": int(latest["plan_id"]),
        "student_level": level,
        "total_items": len(items),
        "completed_items": completed,
        "estimated_completion_days": int(estimated_days),
        "items": items,
        "weak_topics": list(dict.fromkeys([x for x in weak_topics if x]))[:6],
        "strong_topics": list(dict.fromkeys([x for x in strong_topics if x]))[:6],
        "ai_explanation": ai_expl,
    }
    return {"request_id": request.state.request_id, "data": payload, "error": None}


@router.get("/learning-plans/{user_id}/latest")
def learning_plan_latest(request: Request, user_id: int, db: Session = Depends(get_db), classroom_id: int | None = None):
    data = get_latest_plan(db, user_id=int(user_id), classroom_id=classroom_id)
    if not data:
        raise HTTPException(status_code=404, detail="No learning plan found")
    out = LearningPlanLatestResponse(**data).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.post("/learning-plans/{plan_id}/tasks/complete")
def learning_plan_task_complete(
    request: Request,
    plan_id: int,
    payload: TaskCompleteRequest,
    db: Session = Depends(get_db),
):
    try:
        data = set_task_completion(
            db,
            plan_id=int(plan_id),
            day_index=int(payload.day_index),
            task_index=int(payload.task_index),
            completed=bool(payload.completed),
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/learning-plans/{plan_id}/homework/grade")
def learning_plan_homework_grade(
    request: Request,
    plan_id: int,
    payload: HomeworkGradeFromPlanRequest,
    db: Session = Depends(get_db),
):
    try:
        data = grade_homework_from_plan(
            db,
            plan_id=int(plan_id),
            user_id=int(payload.user_id),
            day_index=int(payload.day_index),
            answer_text=str(payload.answer_text or ""),
            mcq_answers=getattr(payload, "mcq_answers", None),
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/learning-plans/{plan_id}/homework/{user_id}/{day_index}")
def learning_plan_homework_get(
    request: Request,
    plan_id: int,
    user_id: int,
    day_index: int,
    db: Session = Depends(get_db),
):
    data = get_homework_submission(db, plan_id=int(plan_id), user_id=int(user_id), day_index=int(day_index))
    if not data:
        raise HTTPException(status_code=404, detail="No homework submission found")
    return {"request_id": request.state.request_id, "data": data, "error": None}
