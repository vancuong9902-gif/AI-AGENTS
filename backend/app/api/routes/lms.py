from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.attempt import Attempt
from app.models.classroom_assessment import ClassroomAssessment
from app.models.document_topic import DocumentTopic
from app.models.quiz_set import QuizSet
from app.models.question import Question
from app.models.learner_profile import LearnerProfile
from app.models.learning_plan import LearningPlan
from app.models.session import Session as UserSession
from app.services.assessment_service import generate_assessment, submit_assessment
from app.services.lms_service import (
    analyze_topic_weak_points,
    build_recommendations,
    classify_student_level,
    generate_class_narrative,
    score_breakdown,
)


router = APIRouter(tags=["lms"])


class TeacherTopicSelectionIn(BaseModel):
    teacher_id: int
    classroom_id: int
    document_id: int
    topics: list[str] = Field(default_factory=list)


class GenerateLmsQuizIn(BaseModel):
    teacher_id: int
    classroom_id: int
    document_ids: list[int] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    title: str = "Placement Test"
    easy_count: int = 4
    medium_count: int = 4
    hard_count: int = 2


class SubmitAttemptIn(BaseModel):
    user_id: int
    duration_sec: int = 0
    answers: list[dict] = Field(default_factory=list)


class PlacementQuizIn(BaseModel):
    topic_ids: list[int] = Field(default_factory=list)
    difficulty_settings: dict[str, int] = Field(
        default_factory=lambda: {"easy": 4, "medium": 4, "hard": 2})
    duration_seconds: int = 1800
    teacher_id: int = 1
    classroom_id: int = 1


class StartAttemptIn(BaseModel):
    quiz_id: int
    student_id: int


class SubmitAttemptByIdIn(BaseModel):
    answers: list[dict] = Field(default_factory=list)


class AssignLearningPathIn(BaseModel):
    student_level: str
    classroom_id: int
    document_ids: list[int] = Field(default_factory=list)


@router.post("/lms/teacher/select-topics")
def teacher_select_topics(request: Request, payload: TeacherTopicSelectionIn, db: Session = Depends(get_db)):
    if not payload.topics:
        raise HTTPException(
            status_code=400, detail="Vui lòng chọn ít nhất 1 topic")

    existing = {
        str(r[0]).strip().lower()
        for r in db.query(DocumentTopic.title).filter(DocumentTopic.document_id == int(payload.document_id)).all()
    }
    selected = [t.strip() for t in payload.topics if t and t.strip()]
    missing = [t for t in selected if t.strip().lower() not in existing]
    return {
        "request_id": request.state.request_id,
        "data": {
            "teacher_id": payload.teacher_id,
            "classroom_id": payload.classroom_id,
            "document_id": payload.document_id,
            "selected_topics": selected,
            "missing_topics": missing,
            "status": "ok",
        },
        "error": None,
    }


def _generate_assessment_lms(*, request: Request, db: Session, payload: GenerateLmsQuizIn, kind: str):
    data = generate_assessment(
        db,
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        title=payload.title,
        level="intermediate",
        kind=kind,
        easy_count=int(payload.easy_count + payload.medium_count),
        hard_count=int(payload.hard_count),
        document_ids=[int(x) for x in payload.document_ids],
        topics=payload.topics,
    )
    data["difficulty_plan"] = {
        "easy": int(payload.easy_count),
        "medium": int(payload.medium_count),
        "hard": int(payload.hard_count),
    }
    return {"request_id": request.state.request_id, "data": data, "error": None}


def _quiz_duration_map(quiz: QuizSet) -> int:
    level_text = str(getattr(quiz, "level", "") or "")
    if "duration=" in level_text:
        try:
            return int(level_text.split("duration=", 1)[1].split(";", 1)[0].strip())
        except Exception:
            return 1800
    return 1800


@router.post("/lms/placement/generate")
def lms_generate_placement(request: Request, payload: GenerateLmsQuizIn, db: Session = Depends(get_db)):
    payload.title = payload.title or "Placement Test"
    return _generate_assessment_lms(request=request, db=db, payload=payload, kind="diagnostic_pre")


@router.post("/lms/final/generate")
def lms_generate_final(request: Request, payload: GenerateLmsQuizIn, db: Session = Depends(get_db)):
    payload.title = payload.title or "Final Test"

    placement_ids: list[int] = []
    try:
        placement_rows = (
            db.query(Attempt.quiz_set_id)
            .join(QuizSet, QuizSet.id == Attempt.quiz_set_id)
            .filter(
                Attempt.user_id == int(payload.teacher_id),
                QuizSet.kind == "diagnostic_pre",
            )
            .distinct()
            .all()
        )
        placement_ids = [int(r[0]) for r in placement_rows]
    except Exception:
        placement_ids = []

    data = generate_assessment(
        db,
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        title=payload.title,
        level="intermediate",
        kind="diagnostic_post",
        easy_count=int(payload.easy_count + payload.medium_count),
        hard_count=int(payload.hard_count),
        document_ids=[int(x) for x in payload.document_ids],
        topics=payload.topics,
        exclude_quiz_ids=placement_ids,
        similarity_threshold=0.75,
    )
    data["difficulty_plan"] = {
        "easy": int(payload.easy_count),
        "medium": int(payload.medium_count),
        "hard": int(payload.hard_count),
    }
    data["excluded_from_count"] = len(placement_ids)
    return {"request_id": request.state.request_id, "data": data, "error": None}


@router.get("/lms/debug/quiz-overlap/{id1}/{id2}")
def debug_quiz_overlap(request: Request, id1: int, id2: int, db: Session = Depends(get_db)):
    from difflib import SequenceMatcher

    s1 = [str(r[0] or "") for r in db.query(Question.stem).filter(Question.quiz_set_id == id1).all()]
    s2 = [str(r[0] or "") for r in db.query(Question.stem).filter(Question.quiz_set_id == id2).all()]

    dups: list[dict[str, object]] = []
    for a in s1:
        for b in s2:
            ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
            if ratio >= 0.75:
                dups.append({"s1": a[:80], "s2": b[:80], "sim": round(float(ratio), 3)})

    return {
        "request_id": request.state.request_id,
        "data": {
            "overlap_count": len(dups),
            "overlap_pct": round(len(dups) / max(1, len(s1)) * 100, 1),
            "quiz1_total": len(s1),
            "quiz2_total": len(s2),
            "samples": dups[:10],
        },
        "error": None,
    }


@router.post("/quizzes/placement")
def create_placement_quiz(request: Request, payload: PlacementQuizIn, db: Session = Depends(get_db)):
    topics = [
        str(r[0])
        for r in db.query(DocumentTopic.title)
        .filter(DocumentTopic.id.in_([int(tid) for tid in payload.topic_ids]))
        .all()
    ]
    req = GenerateLmsQuizIn(
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        topics=topics,
        title="Placement Test",
        easy_count=int(payload.difficulty_settings.get("easy", 4)),
        medium_count=int(payload.difficulty_settings.get("medium", 4)),
        hard_count=int(payload.difficulty_settings.get("hard", 2)),
    )
    response = _generate_assessment_lms(
        request=request, db=db, payload=req, kind="diagnostic_pre")
    quiz_id = int((response.get("data") or {}).get("assessment_id") or 0)
    if quiz_id > 0:
        quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
        if quiz:
            quiz.level = f"{quiz.level};duration={int(payload.duration_seconds)}"
            db.commit()
    response["data"]["duration_seconds"] = int(payload.duration_seconds)
    response["data"]["quiz_type"] = "placement"
    return response


@router.post("/quizzes/final")
def create_final_quiz(request: Request, payload: PlacementQuizIn, db: Session = Depends(get_db)):
    topics = [
        str(r[0])
        for r in db.query(DocumentTopic.title)
        .filter(DocumentTopic.id.in_([int(tid) for tid in payload.topic_ids]))
        .all()
    ]
    req = GenerateLmsQuizIn(
        teacher_id=int(payload.teacher_id),
        classroom_id=int(payload.classroom_id),
        topics=topics,
        title="Final Test",
        easy_count=int(payload.difficulty_settings.get("easy", 4)),
        medium_count=int(payload.difficulty_settings.get("medium", 4)),
        hard_count=int(payload.difficulty_settings.get("hard", 2)),
    )
    response = _generate_assessment_lms(
        request=request, db=db, payload=req, kind="diagnostic_post")
    quiz_id = int((response.get("data") or {}).get("assessment_id") or 0)
    if quiz_id > 0:
        quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
        if quiz:
            quiz.level = f"{quiz.level};duration={int(payload.duration_seconds)}"
            db.commit()
    response["data"]["duration_seconds"] = int(payload.duration_seconds)
    response["data"]["quiz_type"] = "final"
    return response


@router.post("/attempts/start")
def start_attempt(request: Request, payload: StartAttemptIn, db: Session = Depends(get_db)):
    session = UserSession(user_id=int(payload.student_id),
                          type=f"quiz_attempt:{int(payload.quiz_id)}")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "request_id": request.state.request_id,
        "data": {
            "attempt_id": int(session.id),
            "quiz_id": int(payload.quiz_id),
            "student_id": int(payload.student_id),
            "start_time": session.started_at.isoformat() if session.started_at else datetime.now(timezone.utc).isoformat(),
        },
        "error": None,
    }


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt_by_id(request: Request, attempt_id: int, payload: SubmitAttemptByIdIn, db: Session = Depends(get_db)):
    started = db.query(UserSession).filter(
        UserSession.id == int(attempt_id)).first()
    if not started or not str(started.type or "").startswith("quiz_attempt:"):
        raise HTTPException(status_code=404, detail="Attempt not found")
    quiz_id = int(str(started.type).split(":", 1)[1])
    quiz = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    duration_seconds = _quiz_duration_map(quiz)
    now = datetime.now(timezone.utc)
    started_at = (started.started_at or now)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    spent = max(0, int((now - started_at).total_seconds()))
    timed_out = spent > int(duration_seconds)

    base = submit_assessment(
        db,
        assessment_id=quiz_id,
        user_id=int(started.user_id),
        duration_sec=spent,
        answers=payload.answers,
    )
    breakdown = score_breakdown(base.get("breakdown") or [])
    level = classify_student_level(
        int(round(float(breakdown["overall"]["percent"]))))
    topics = [str(x) for x in (quiz.topic.split(
        ",") if quiz.topic else []) if x.strip()]
    recommendations = build_recommendations(
        breakdown=breakdown, document_topics=topics)

    if timed_out:
        base["notes"] = "Nộp quá thời gian; hệ thống chấm theo câu trả lời tại thời điểm nộp."
    return {
        "request_id": request.state.request_id,
        "data": {
            **base,
            "time_spent_seconds": spent,
            "duration_seconds": duration_seconds,
            "timed_out": timed_out,
            "score_breakdown": breakdown,
            "classification": level,
            "recommendations": recommendations,
        },
        "error": None,
    }


@router.post("/lms/student/{user_id}/assign-learning-path")
def assign_student_path(
    request: Request,
    user_id: int,
    payload: AssignLearningPathIn,
    db: Session = Depends(get_db),
):
    result = assign_learning_path(
        db,
        user_id=int(user_id),
        student_level=str(payload.student_level),
        document_ids=[int(x) for x in (payload.document_ids or [])],
        classroom_id=int(payload.classroom_id),
    )
    return {"request_id": request.state.request_id, "data": result, "error": None}


@router.get("/lms/student/{user_id}/my-path")
def get_student_path(request: Request, user_id: int, db: Session = Depends(get_db)):
    profile = db.query(LearnerProfile).filter(
        LearnerProfile.user_id == int(user_id)).first()
    plan = db.query(LearningPlan).filter(LearningPlan.user_id == int(
        user_id)).order_by(LearningPlan.id.desc()).first()
    tasks = []
    if plan and isinstance(plan.plan_json, dict):
        tasks = plan.plan_json.get("tasks") or []

    return {
        "request_id": request.state.request_id,
        "data": {
            "student_level": profile.level if profile else None,
            "plan": {
                "plan_id": int(plan.id) if plan else None,
                "tasks": tasks,
            },
        },
        "error": None,
    }


@router.get("/students/{student_id}/recommendations")
def student_recommendations(request: Request, student_id: int, db: Session = Depends(get_db)):
    latest = (
        db.query(Attempt)
        .filter(Attempt.user_id == int(student_id))
        .order_by(Attempt.created_at.desc())
        .first()
    )
    if not latest:
        return {"request_id": request.state.request_id, "data": {"student_id": student_id, "recommendations": []}, "error": None}
    breakdown = score_breakdown(latest.breakdown_json or [])
    quiz = db.query(QuizSet).filter(
        QuizSet.id == int(latest.quiz_set_id)).first()
    topics = [str(x) for x in (quiz.topic.split(
        ",") if quiz and quiz.topic else []) if x.strip()]
    recs = build_recommendations(breakdown=breakdown, document_topics=topics)
    assignments = [
        {"topic": r["topic"], "material": r["material"],
            "exercise_set": r["exercise"], "status": "assigned"}
        for r in recs
    ]
    return {"request_id": request.state.request_id, "data": {"student_id": student_id, "recommendations": recs, "assignments": assignments}, "error": None}


@router.get("/teacher/reports")
def teacher_reports(request: Request, classroom_id: int = 1, db: Session = Depends(get_db)):
    return teacher_report(request=request, classroom_id=classroom_id, db=db)


@router.post("/lms/attempts/{assessment_id}/submit")
def lms_submit_attempt(request: Request, assessment_id: int, payload: SubmitAttemptIn, db: Session = Depends(get_db)):
    base = submit_assessment(
        db,
        assessment_id=int(assessment_id),
        user_id=int(payload.user_id),
        duration_sec=int(payload.duration_sec),
        answers=payload.answers,
    )

    breakdown = score_breakdown(base.get("breakdown") or [])
    level = classify_student_level(
        int(round(float(breakdown["overall"]["percent"]))))

    q = db.query(QuizSet).filter(QuizSet.id == int(assessment_id)).first()
    topics = [str(x) for x in (q.topic.split(
        ",") if q and q.topic else []) if x.strip()]
    recommendations = build_recommendations(
        breakdown=breakdown, document_topics=topics)

    try:
        q_obj = db.query(QuizSet).filter(
            QuizSet.id == int(assessment_id)).first()
        doc_ids: list[int] = []
        if q_obj:
            raw_doc_ids = getattr(q_obj, "document_ids_json", None)
            if isinstance(raw_doc_ids, list):
                doc_ids = [int(x) for x in raw_doc_ids if x]
        if doc_ids and level:
            path_result = assign_learning_path(
                db,
                user_id=int(payload.user_id),
                student_level=level,
                document_ids=doc_ids,
                classroom_id=0,
            )
            base["assigned_learning_path"] = path_result
    except Exception:
        base["assigned_learning_path"] = None

    base["score_breakdown"] = breakdown
    base["student_level"] = level
    base["recommendations"] = recommendations
    return {"request_id": request.state.request_id, "data": base, "error": None}


@router.get("/lms/teacher/report/{classroom_id}")
def teacher_report(request: Request, classroom_id: int, db: Session = Depends(get_db)):
    assessment_ids = [
        int(r[0])
        for r in db.query(ClassroomAssessment.assessment_id)
        .filter(ClassroomAssessment.classroom_id == int(classroom_id))
        .all()
    ]
    if not assessment_ids:
        return {
            "request_id": request.state.request_id,
            "data": {
                "rows": [],
                "summary": {"students": 0, "avg_percent": 0.0, "level_distribution": {}, "avg_improvement": 0.0},
                "ai_narrative": "",
                "weak_topics": [],
                "progress_chart": [],
            },
            "error": None,
        }

    attempts = db.query(Attempt).filter(
        Attempt.quiz_set_id.in_(assessment_ids)).all()
    by_student: dict[int, list[float]] = defaultdict(list)
    by_level: dict[str, int] = defaultdict(int)

    progress_chart: list[dict] = []
    pre_scores: dict[int, float] = {}
    post_scores: dict[int, float] = {}
    all_breakdowns: list[dict] = []

    quiz_kind_map = {
        int(qid): str(kind or "")
        for qid, kind in db.query(QuizSet.id, QuizSet.kind).filter(QuizSet.id.in_(assessment_ids)).all()
    }

    for at in attempts:
        br = score_breakdown(at.breakdown_json or [])
        all_breakdowns.append(br)
        pct = float(br["overall"]["percent"])
        uid = int(at.user_id)
        by_student[uid].append(pct)
        by_level[classify_student_level(int(round(pct)))] += 1

        kind = quiz_kind_map.get(int(at.quiz_set_id), "")
        if kind == "diagnostic_pre":
            pre_scores[uid] = pct
        elif kind == "diagnostic_post":
            post_scores[uid] = pct

    rows = []
    for uid, vals in sorted(by_student.items()):
        avg = round(sum(vals) / max(1, len(vals)), 2)
        rows.append({"student_id": uid, "attempts": len(
            vals), "avg_percent": avg, "level": classify_student_level(int(round(avg)))})

    all_uids = sorted(set(pre_scores.keys()) | set(post_scores.keys()))
    for uid in all_uids:
        pre_score = round(float(pre_scores.get(uid, 0.0)), 1)
        post_score = round(float(post_scores.get(uid, 0.0)), 1)
        progress_chart.append(
            {
                "student_id": uid,
                "pre_score": pre_score,
                "post_score": post_score,
                "delta": round(post_score - pre_score, 1),
            }
        )

    weak_topics = analyze_topic_weak_points(all_breakdowns)
    level_distribution = dict(by_level)

    deltas = [d["delta"] for d in progress_chart if pre_scores.get(d["student_id"], 0) > 0]
    avg_improvement = sum(deltas) / max(1, len(deltas))

    narrative = generate_class_narrative(
        total_students=len(rows),
        level_dist=level_distribution,
        weak_topics=weak_topics[:3],
        avg_improvement=avg_improvement,
    )

    return {
        "request_id": request.state.request_id,
        "data": {
            "rows": rows,
            "summary": {"students": len(rows), "avg_percent": round(sum((r["avg_percent"] for r in rows), 0.0) / max(1, len(rows)), 1), "level_distribution": dict(by_level), "avg_improvement": round(avg_improvement, 1)},
            "ai_narrative": narrative,
            "weak_topics": weak_topics[:5],
            "progress_chart": progress_chart,
        },
        "error": None,
    }
