from __future__ import annotations

from collections import defaultdict
from statistics import mean

from app.db.session import SessionLocal
from app.models.attempt import Attempt
from app.models.class_report import ClassReport
from app.models.classroom import ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.models.quiz_set import QuizSet
from app.services.lms_service import (
    analyze_topic_weak_points,
    generate_class_narrative,
    per_student_bloom_analysis,
    score_breakdown,
)
from app.services.teacher_report_export_service import build_classroom_report_pdf


def _pick_latest_attempts(attempts: list[Attempt]) -> list[Attempt]:
    latest_by_user: dict[int, Attempt] = {}
    for at in sorted(attempts, key=lambda x: x.created_at or 0, reverse=True):
        uid = int(at.user_id)
        if uid not in latest_by_user:
            latest_by_user[uid] = at
    return list(latest_by_user.values())


def _calc_improvement(entry_attempts: list[Attempt], final_attempts: list[Attempt]) -> dict:
    entry_latest = {int(a.user_id): a for a in _pick_latest_attempts(entry_attempts)}
    final_latest = {int(a.user_id): a for a in _pick_latest_attempts(final_attempts)}

    rows = []
    deltas: list[float] = []
    for uid, fat in final_latest.items():
        pre = entry_latest.get(uid)
        pre_score = float(pre.score_percent) if pre else None
        post_score = float(fat.score_percent)
        delta = (post_score - pre_score) if pre_score is not None else None
        if delta is not None:
            deltas.append(delta)
        rows.append(
            {
                "student_id": int(uid),
                "entry_score": pre_score,
                "final_score": post_score,
                "delta": delta,
            }
        )

    return {
        "avg_delta": round(mean(deltas), 2) if deltas else 0.0,
        "students": rows,
    }


def task_generate_class_final_report(classroom_id: int, assessment_id: int) -> dict:
    db = SessionLocal()
    try:
        final_attempts = (
            db.query(Attempt)
            .join(ClassroomMember, ClassroomMember.user_id == Attempt.user_id)
            .filter(ClassroomMember.classroom_id == int(classroom_id), Attempt.quiz_set_id == int(assessment_id))
            .all()
        )
        latest_final_attempts = _pick_latest_attempts(final_attempts)
        if not latest_final_attempts:
            return {"created": False, "reason": "no_attempts"}

        all_breakdowns = [score_breakdown(list(a.breakdown_json or [])) for a in latest_final_attempts]
        merged_breakdown = score_breakdown([item for a in latest_final_attempts for item in (a.breakdown_json or [])])
        weak_topics = analyze_topic_weak_points(all_breakdowns)[:3]

        level_dist = {"yeu": 0, "trung_binh": 0, "kha": 0, "gioi": 0}
        for at in latest_final_attempts:
            sc = float(at.score_percent or 0)
            if sc < 50:
                level_dist["yeu"] += 1
            elif sc < 65:
                level_dist["trung_binh"] += 1
            elif sc < 80:
                level_dist["kha"] += 1
            else:
                level_dist["gioi"] += 1

        entry_exam_ids = [
            int(r[0])
            for r in (
                db.query(ClassroomAssessment.assessment_id)
                .join(QuizSet, QuizSet.id == ClassroomAssessment.assessment_id)
                .filter(ClassroomAssessment.classroom_id == int(classroom_id), QuizSet.kind.in_(["entry_test", "diagnostic_pre"]))
                .all()
            )
            if r and r[0] is not None
        ]

        entry_attempts = (
            db.query(Attempt)
            .join(ClassroomMember, ClassroomMember.user_id == Attempt.user_id)
            .filter(ClassroomMember.classroom_id == int(classroom_id), Attempt.quiz_set_id.in_(entry_exam_ids))
            .all()
            if entry_exam_ids
            else []
        )
        improvement_data = _calc_improvement(entry_attempts, latest_final_attempts)

        per_student = per_student_bloom_analysis(latest_final_attempts, quiz_kind_map={})
        narrative = generate_class_narrative(
            total_students=len(latest_final_attempts),
            level_dist=level_dist,
            weak_topics=weak_topics,
            avg_improvement=float(improvement_data.get("avg_delta") or 0.0),
            per_student_data=per_student,
        )

        report = (
            db.query(ClassReport)
            .filter(ClassReport.classroom_id == int(classroom_id), ClassReport.assessment_id == int(assessment_id))
            .first()
        )
        payload_stats = {
            "summary": merged_breakdown,
            "level_distribution": level_dist,
            "weak_topics": weak_topics,
            "total_students": len(latest_final_attempts),
        }
        if report:
            report.narrative = narrative
            report.stats_json = payload_stats
            report.improvement_json = improvement_data
        else:
            report = ClassReport(
                classroom_id=int(classroom_id),
                assessment_id=int(assessment_id),
                narrative=narrative,
                stats_json=payload_stats,
                improvement_json=improvement_data,
            )
            db.add(report)
        db.commit()
        db.refresh(report)
        return {"created": True, "report_id": int(report.id)}
    finally:
        db.close()


def task_export_teacher_report_pdf(classroom_id: int) -> dict:
    db = SessionLocal()
    try:
        path = build_classroom_report_pdf(classroom_id=int(classroom_id), db=db)
        return {"classroom_id": int(classroom_id), "pdf_path": path}
    finally:
        db.close()
