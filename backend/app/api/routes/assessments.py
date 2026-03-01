from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_teacher, require_user
from app.db.session import get_db
from app.models.classroom import Classroom, ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.models.attempt import Attempt
from app.models.class_report import ClassReport
from app.models.quiz_set import QuizSet
from app.models.notification import Notification
from app.models.learning_plan import LearningPlan, LearningPlanTaskCompletion
from app.models.user import User
from app.infra.queue import enqueue
from app.tasks.report_tasks import task_generate_class_final_report
from app.services.llm_service import chat_text, llm_available
from app.schemas.assessment import (
    AssessmentGenerateRequest,
    AssessmentSubmitRequest,
    TeacherGradeRequest,
)
from app.api.routes.lms import collect_excluded_quiz_ids_for_classroom_final
from app.services.assessment_service import (
    generate_assessment,
    generate_diagnostic_assessment,
    get_assessment,
    submit_assessment,
    start_assessment_session,
    list_assessments_for_teacher,
    list_assessments_for_user,
    list_assessments_by_type,
    leaderboard_for_assessment,
    grade_essays,
    get_latest_submission,
    get_or_generate_attempt_explanations,
)


def _mark_assessment_completion_in_learning_plan(db: Session, *, user_id: int, assessment_id: int) -> None:
    latest_plan = (
        db.query(LearningPlan)
        .filter(LearningPlan.user_id == int(user_id))
        .order_by(LearningPlan.id.desc())
        .first()
    )
    if not latest_plan:
        return

    plan_json = latest_plan.plan_json if isinstance(latest_plan.plan_json, dict) else {}
    assigned_tasks = plan_json.get("assigned_tasks") if isinstance(plan_json.get("assigned_tasks"), list) else []
    if not assigned_tasks:
        return

    matched_topic_ids = {
        int(t.get("topic_id"))
        for t in assigned_tasks
        if str(t.get("quiz_id") or "").isdigit() and int(t.get("quiz_id")) == int(assessment_id) and str(t.get("topic_id") or "").isdigit()
    }
    if not matched_topic_ids:
        return

    days = plan_json.get("days") if isinstance(plan_json.get("days"), list) else []
    changed = False
    for day in days:
        if not isinstance(day, dict):
            continue
        day_index = int(day.get("day_index") or 0)
        if day_index <= 0:
            continue
        tasks = day.get("tasks") if isinstance(day.get("tasks"), list) else []
        for task_index, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            topic_id = task.get("topic_id")
            if not (str(topic_id).isdigit() and int(topic_id) in matched_topic_ids):
                continue

            row = (
                db.query(LearningPlanTaskCompletion)
                .filter(
                    LearningPlanTaskCompletion.plan_id == int(latest_plan.id),
                    LearningPlanTaskCompletion.day_index == int(day_index),
                    LearningPlanTaskCompletion.task_index == int(task_index),
                )
                .first()
            )
            if row is None:
                row = LearningPlanTaskCompletion(
                    plan_id=int(latest_plan.id),
                    day_index=int(day_index),
                    task_index=int(task_index),
                    completed=True,
                )
                db.add(row)
                changed = True
            elif not bool(row.completed):
                row.completed = True
                changed = True

    if changed:
        db.flush()

router = APIRouter(tags=["assessments"])
teacher_router = APIRouter(tags=["teacher"])

_RECOMMENDATION_CACHE: dict[tuple[str, str, str], str] = {}


def _classify_percentage(percentage: float) -> tuple[str, str]:
    pct = float(percentage or 0)
    if pct >= 85:
        return "gioi", "Giỏi"
    if pct >= 70:
        return "kha", "Khá"
    if pct >= 50:
        return "trung_binh", "Trung Bình"
    return "yeu", "Yếu"


def _difficulty_breakdown(answer_review: list[dict]) -> dict:
    buckets = {
        "easy": {"correct": 0, "total": 0, "percentage": 0.0},
        "medium": {"correct": 0, "total": 0, "percentage": 0.0},
        "hard": {"correct": 0, "total": 0, "percentage": 0.0},
    }
    for item in answer_review:
        key = str(item.get("difficulty") or "medium").lower()
        if key not in buckets:
            key = "medium"
        buckets[key]["total"] += 1
        if item.get("is_correct"):
            buckets[key]["correct"] += 1

    for key in buckets:
        total = int(buckets[key]["total"])
        correct = int(buckets[key]["correct"])
        buckets[key]["percentage"] = round((correct / max(1, total)) * 100, 1)
    return buckets


def _topic_breakdown(answer_review: list[dict]) -> list[dict]:
    topic_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    for item in answer_review:
        topic = str(item.get("topic") or "Chưa phân loại").strip() or "Chưa phân loại"
        topic_stats[topic]["total"] += 1
        if item.get("is_correct"):
            topic_stats[topic]["correct"] += 1

    rows = []
    for topic, stats in topic_stats.items():
        total = int(stats["total"])
        correct = int(stats["correct"])
        percentage = round((correct / max(1, total)) * 100, 1)
        rows.append(
            {
                "topic": topic,
                "correct": correct,
                "total": total,
                "percentage": percentage,
                "weak": bool(percentage < 50),
            }
        )
    rows.sort(key=lambda x: x["percentage"])
    return rows


def _recommendation_text(*, percentage: float, classification_label: str, topics: list[dict]) -> str:
    weak_topics = [t["topic"] for t in topics if float(t.get("percentage") or 0) < 50]
    strong_topics = [t["topic"] for t in topics if float(t.get("percentage") or 0) >= 80]

    weak_text = ", ".join(weak_topics[:4]) or "các nền tảng còn yếu"
    strong_text = ", ".join(strong_topics[:4]) or "một số chủ đề cốt lõi"
    cache_key = (classification_label.lower(), weak_text, strong_text)

    if not llm_available():
        if cache_key not in _RECOMMENDATION_CACHE:
            _RECOMMENDATION_CACHE[cache_key] = f"Tiếp tục ôn luyện {weak_text}. Bạn làm tốt ở {strong_text}."
        return _RECOMMENDATION_CACHE[cache_key]

    prompt = (
        f"Học sinh đạt {round(float(percentage or 0), 1)}% ({classification_label}).\n"
        f"Điểm yếu: {weak_text}. Điểm mạnh: {strong_text}.\n"
        "Viết 2-3 câu khuyến nghị học tập bằng tiếng Việt, ngắn gọn, cụ thể.\n"
        "Không dùng từ 'bạn' quá nhiều. Tập trung vào action items."
    )
    try:
        output = chat_text(
            messages=[
                {"role": "system", "content": "Bạn là trợ lý học tập tiếng Việt, trả lời ngắn gọn và thực tế."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=180,
            timeout_sec=1.2,
        )
        cleaned = str(output or "").strip()
        if cleaned:
            return cleaned
    except Exception:
        pass

    if cache_key not in _RECOMMENDATION_CACHE:
        _RECOMMENDATION_CACHE[cache_key] = f"Tiếp tục ôn luyện {weak_text}. Bạn làm tốt ở {strong_text}."
    return _RECOMMENDATION_CACHE[cache_key]


def _build_detailed_result(raw: dict) -> dict:
    answer_review = list(raw.get("answer_review") or [])
    percentage = round(float(raw.get("total_score_percent") or raw.get("score_percent") or 0), 1)
    classification, classification_label = _classify_percentage(percentage)
    by_difficulty = _difficulty_breakdown(answer_review)
    by_topic = _topic_breakdown(answer_review)

    detailed = {
        "score": int(round(percentage)),
        "max_score": 100,
        "percentage": percentage,
        "classification": classification,
        "classification_label": classification_label,
        "time_taken_seconds": int(raw.get("duration_sec") or 0),
        "breakdown_by_difficulty": by_difficulty,
        "breakdown_by_topic": by_topic,
        "ai_recommendation": _recommendation_text(
            percentage=percentage,
            classification_label=classification_label,
            topics=by_topic,
        ),
    }

    assessment_kind = str(raw.get("assessment_kind") or "").lower()
    if assessment_kind == "final_exam":
        detailed["improvement_vs_diagnostic"] = raw.get("improvement_vs_entry")

    return {**raw, **detailed}




class DiagnosticGenerateRequest(BaseModel):
    classroom_id: int
    topic_ids: list[int] = Field(default_factory=list)
    difficulty_config: dict[str, int] | None = None

def _check_and_trigger_class_report(db: Session, *, assessment_id: int, user_id: int) -> None:
    _ = user_id
    mapping = (
        db.query(ClassroomAssessment, QuizSet)
        .join(QuizSet, QuizSet.id == ClassroomAssessment.assessment_id)
        .filter(ClassroomAssessment.assessment_id == int(assessment_id))
        .first()
    )
    if not mapping:
        return

    classroom_assessment, quiz_set = mapping
    if (quiz_set.kind or "").strip().lower() != "final_exam":
        return

    classroom_id = int(classroom_assessment.classroom_id)
    total_members = (
        db.query(func.count(ClassroomMember.id))
        .filter(ClassroomMember.classroom_id == classroom_id)
        .scalar()
    )
    total_members = int(total_members or 0)
    if total_members <= 0:
        return

    submitted = (
        db.query(func.count(func.distinct(Attempt.user_id)))
        .join(ClassroomMember, ClassroomMember.user_id == Attempt.user_id)
        .filter(ClassroomMember.classroom_id == classroom_id, Attempt.quiz_set_id == int(assessment_id))
        .scalar()
    )
    submitted = int(submitted or 0)
    threshold_reached = (submitted / max(1, total_members)) >= 0.8
    if not threshold_reached:
        return

    exists = (
        db.query(ClassReport.id)
        .filter(ClassReport.classroom_id == classroom_id, ClassReport.assessment_id == int(assessment_id))
        .first()
    )
    if exists:
        return

    enqueue(
        task_generate_class_final_report,
        classroom_id,
        int(assessment_id),
        queue_name="default",
    )




def _notify_teacher_when_all_final_submitted(db: Session, *, assessment_id: int) -> None:
    mapping = (
        db.query(ClassroomAssessment, QuizSet, Classroom)
        .join(QuizSet, QuizSet.id == ClassroomAssessment.assessment_id)
        .join(Classroom, Classroom.id == ClassroomAssessment.classroom_id)
        .filter(ClassroomAssessment.assessment_id == int(assessment_id))
        .first()
    )
    if not mapping:
        return
    classroom_assessment, quiz_set, classroom = mapping
    if str(getattr(quiz_set, "kind", "") or "") not in {"diagnostic_post", "final_exam"}:
        return

    members = [int(uid) for uid, in db.query(ClassroomMember.user_id).filter(ClassroomMember.classroom_id == int(classroom_assessment.classroom_id), ClassroomMember.user_id != int(classroom.teacher_id)).all()]
    if not members:
        return
    submitted = {int(uid) for uid, in db.query(Attempt.user_id).filter(Attempt.quiz_set_id == int(assessment_id), Attempt.user_id.in_(members)).distinct().all()}
    if not set(members).issubset(submitted):
        return

    exists = db.query(Notification.id).filter(Notification.user_id == int(classroom.teacher_id), Notification.type == "class_final_ready", Notification.quiz_id == int(assessment_id)).first()
    if exists:
        return

    db.add(Notification(
        user_id=int(classroom.teacher_id),
        teacher_id=int(classroom.teacher_id),
        quiz_id=int(assessment_id),
        type="class_final_ready",
        title="Báo cáo lớp sẵn sàng",
        message="Tất cả học sinh đã nộp final. Báo cáo sẵn sàng.",
        payload_json={"classroom_id": int(classroom_assessment.classroom_id), "quiz_id": int(assessment_id)},
        is_read=False,
    ))
    db.commit()

def _student_can_access_assessment(db: Session, *, student_id: int, assessment_id: int) -> bool:
    # student must be member of a classroom that has this assessment assigned
    q = (
        db.query(ClassroomAssessment.id)
        .join(ClassroomMember, ClassroomMember.classroom_id == ClassroomAssessment.classroom_id)
        .filter(ClassroomMember.user_id == int(student_id))
        .filter(ClassroomAssessment.assessment_id == int(assessment_id))
        .limit(1)
    )
    return bool(q.first())


@router.post("/assessments/generate")
def assessments_generate(
    request: Request,
    payload: AssessmentGenerateRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    # Validate classroom ownership
    c = db.query(Classroom).filter(Classroom.id == int(payload.classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    exclude_ids = []
    if str(payload.kind or "").lower() in {"diagnostic_post", "final_exam"}:
        exclude_ids = collect_excluded_quiz_ids_for_classroom_final(db, int(payload.classroom_id))

    try:
        data = generate_assessment(
            db,
            teacher_id=int(teacher.id),
            classroom_id=int(payload.classroom_id),
            title=payload.title,
            level=payload.level,
            easy_count=payload.easy_count,
            medium_count=payload.medium_count,
            hard_mcq_count=payload.hard_mcq_count,
            hard_count=payload.hard_count,
            document_ids=payload.document_ids,
            topics=payload.topics,
            kind=payload.kind,
            exclude_quiz_ids=exclude_ids,
            similarity_threshold=0.75,
        )
        if exclude_ids:
            data["excluded_from_count"] = len(exclude_ids)
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))




@router.post("/assessments/generate-diagnostic")
def assessments_generate_diagnostic(
    request: Request,
    payload: DiagnosticGenerateRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    c = db.query(Classroom).filter(Classroom.id == int(payload.classroom_id)).first()
    if not c or int(c.teacher_id) != int(teacher.id):
        raise HTTPException(status_code=404, detail="Classroom not found")

    try:
        data = generate_diagnostic_assessment(
            db,
            teacher_id=int(teacher.id),
            classroom_id=int(payload.classroom_id),
            topic_ids=[int(t) for t in (payload.topic_ids or [])],
            difficulty_config=payload.difficulty_config or {"easy": 5, "medium": 5, "hard": 5},
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/assessments")
def assessments_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    classroom_id: int | None = None,
):
    # Student: list assessments assigned to their class(es)
    if (getattr(user, "role", "student") or "student") == "student":
        data = list_assessments_for_user(db, user_id=int(user.id), classroom_id=classroom_id)
        return {"request_id": request.state.request_id, "data": data, "error": None}

    # Teacher: list across their classes, optionally filtered
    data = list_assessments_for_teacher(db, teacher_id=int(user.id), classroom_id=classroom_id)
    return {"request_id": request.state.request_id, "data": data, "error": None}


@router.get("/assessments/by-type/{kind}")
def get_assessments_by_type(
    kind: str,
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    """Lấy danh sách bài kiểm tra theo loại: diagnostic_pre, final, homework"""
    allowed = {"diagnostic_pre", "final", "homework", "midterm", "final_exam", "entry_test", "diagnostic_post"}
    if kind not in allowed:
        raise HTTPException(status_code=400, detail=f"kind must be one of {allowed}")
    if kind == "homework":
        return {"request_id": request.state.request_id, "data": [], "error": None}

    data = list_assessments_by_type(db, user_id=int(user_id), kind=kind)
    return {"request_id": request.state.request_id, "data": data, "error": None}


@router.get("/assessments/{assessment_id}")
def assessments_get(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # Students can only open assessments assigned to their classroom.
    if (getattr(user, "role", "student") or "student") == "student":
        if not _student_can_access_assessment(db, student_id=int(user.id), assessment_id=int(assessment_id)):
            raise HTTPException(status_code=404, detail="Assessment not found")

    try:
        data = get_assessment(db, assessment_id=assessment_id)
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/assessments/{assessment_id}/start")
def assessments_start(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if (getattr(user, "role", "student") or "student") == "student":
        if not _student_can_access_assessment(db, student_id=int(user.id), assessment_id=int(assessment_id)):
            raise HTTPException(status_code=404, detail="Assessment not found")

    try:
        data = start_assessment_session(db, assessment_id=assessment_id, user_id=int(user.id))
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/assessments/{assessment_id}/submit")
def assessments_submit(
    request: Request,
    assessment_id: int,
    payload: AssessmentSubmitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # Students can only submit assessments assigned to their classroom.
    if (getattr(user, "role", "student") or "student") == "student":
        if not _student_can_access_assessment(db, student_id=int(user.id), assessment_id=int(assessment_id)):
            raise HTTPException(status_code=404, detail="Assessment not found")

    # Always submit as the current user (ignore payload.user_id)
    try:
        data = submit_assessment(
            db,
            assessment_id=assessment_id,
            user_id=int(user.id),
            answers=[a.model_dump() for a in (payload.answers or [])],
            duration_sec=payload.duration_sec,
        )
        data = _build_detailed_result(data)
        _check_and_trigger_class_report(db, assessment_id=assessment_id, user_id=int(user.id))
        _notify_teacher_when_all_final_submitted(db, assessment_id=int(assessment_id))
        _mark_assessment_completion_in_learning_plan(db, user_id=int(user.id), assessment_id=int(assessment_id))
        db.commit()
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/assessments/{assessment_id}/explanations")
def assessments_explanations(
    request: Request,
    assessment_id: int,
    attempt_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if (getattr(user, "role", "student") or "student") == "student":
        if not _student_can_access_assessment(db, student_id=int(user.id), assessment_id=int(assessment_id)):
            raise HTTPException(status_code=404, detail="Assessment not found")

    try:
        data = get_or_generate_attempt_explanations(
            db,
            assessment_id=int(assessment_id),
            user_id=int(user.id),
            attempt_id=int(attempt_id) if attempt_id is not None else None,
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/assessments/quiz-sets/{quiz_set_id}/start")
def quiz_set_start(
    request: Request,
    quiz_set_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if (getattr(user, "role", "student") or "student") == "student":
        if not _student_can_access_assessment(db, student_id=int(user.id), assessment_id=int(quiz_set_id)):
            raise HTTPException(status_code=404, detail="Assessment not found")

    try:
        data = start_assessment_session(db, assessment_id=int(quiz_set_id), user_id=int(user.id))
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/assessments/quiz-sets/{quiz_set_id}/submit")
def assessments_submit_quiz_set(
    request: Request,
    quiz_set_id: int,
    payload: AssessmentSubmitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if (getattr(user, "role", "student") or "student") == "student":
        if not _student_can_access_assessment(db, student_id=int(user.id), assessment_id=int(quiz_set_id)):
            raise HTTPException(status_code=404, detail="Assessment not found")

    try:
        data = submit_assessment(
            db,
            assessment_id=int(quiz_set_id),
            user_id=int(user.id),
            answers=[a.model_dump() for a in (payload.answers or [])],
            duration_sec=payload.duration_sec,
        )
        _check_and_trigger_class_report(db, assessment_id=int(quiz_set_id), user_id=int(user.id))
        _notify_teacher_when_all_final_submitted(db, assessment_id=int(quiz_set_id))
        _mark_assessment_completion_in_learning_plan(db, user_id=int(user.id), assessment_id=int(quiz_set_id))
        db.commit()
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return assessments_submit(request=request, assessment_id=quiz_set_id, payload=payload, db=db, user=user)
# -----------------------
# Teacher endpoints
# -----------------------


@teacher_router.get("/teacher/assessments")
def teacher_assessments_list(
    request: Request,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
    classroom_id: int | None = None,
):
    data = list_assessments_for_teacher(db, teacher_id=int(teacher.id), classroom_id=classroom_id)
    return {"request_id": request.state.request_id, "data": data, "error": None}


@teacher_router.get("/teacher/assessments/{assessment_id}/leaderboard")
def teacher_assessment_leaderboard(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    # (Optional) could validate ownership via classroom mapping; keep permissive for demo.
    try:
        data = leaderboard_for_assessment(db, assessment_id=assessment_id)
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@teacher_router.get("/teacher/assessments/{assessment_id}/submissions/{student_id}")
def teacher_latest_submission(
    request: Request,
    assessment_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    try:
        data = get_latest_submission(db, assessment_id=assessment_id, student_id=student_id)
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@teacher_router.post("/teacher/assessments/{assessment_id}/grade")
def teacher_grade_essays(
    request: Request,
    assessment_id: int,
    payload: TeacherGradeRequest,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    try:
        data = grade_essays(
            db,
            assessment_id=assessment_id,
            student_id=payload.student_id,
            grades=[g.model_dump() for g in (payload.grades or [])],
        )
        return {"request_id": request.state.request_id, "data": data, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
