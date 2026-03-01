from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _level_from_score(score: float) -> str:
    if score >= 85:
        return "advanced"
    if score >= 70:
        return "intermediate"
    if score >= 50:
        return "basic"
    return "needs_support"


def _iso_date(value: Any) -> str:
    if not value:
        return "unknown"
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date().isoformat()
        except ValueError:
            continue
    return text[:10]


def build_teacher_analytics_report(
    class_roster: list[dict[str, Any]] | None = None,
    attempts: list[dict[str, Any]] | None = None,
    learning_time_logs: list[dict[str, Any]] | None = None,
    pre_vs_post: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    class_roster = class_roster or []
    attempts = attempts or []
    learning_time_logs = learning_time_logs or []
    pre_vs_post = pre_vs_post or []

    roster_by_id: dict[Any, dict[str, Any]] = {s.get("student_id"): s for s in class_roster if s.get("student_id") is not None}

    # Study hours by student
    study_hours: dict[Any, float] = defaultdict(float)
    for log in learning_time_logs:
        sid = log.get("student_id")
        if sid is None:
            continue
        study_hours[sid] += _safe_float(log.get("hours"), 0.0)

    # Scores over time and topic mastery
    scores_by_date: dict[str, list[float]] = defaultdict(list)
    topic_mastery_heatmap: list[dict[str, Any]] = []
    latest_score_by_student: dict[Any, float] = {}

    for attempt in attempts:
        sid = attempt.get("student_id")
        score = _safe_float(attempt.get("score"))
        date = _iso_date(attempt.get("submitted_at") or attempt.get("date"))
        scores_by_date[date].append(score)
        if sid is not None:
            latest_score_by_student[sid] = score

        for item in (attempt.get("breakdown") or []):
            topic = item.get("topic")
            if not topic or sid is None:
                continue
            topic_mastery_heatmap.append(
                {
                    "student_id": sid,
                    "topic": topic,
                    "percent": round(_safe_float(item.get("percent")), 2),
                }
            )

    # Pre vs post progress + weak topic collection
    progress_values: list[float] = []
    weak_topic_counter: Counter[str] = Counter()

    for row in pre_vs_post:
        pre = _safe_float(row.get("pre_score"))
        post = _safe_float(row.get("post_score"))
        progress_values.append(post - pre)
        for topic_name, topic_score in (row.get("topic_scores") or {}).items():
            if _safe_float(topic_score) < 65:
                weak_topic_counter[str(topic_name)] += 1

    # Level distribution: from latest score if available, else placement/average score from roster
    level_counter: Counter[str] = Counter()
    if roster_by_id:
        for sid, student in roster_by_id.items():
            score = latest_score_by_student.get(sid)
            if score is None:
                score = _safe_float(student.get("score"), 0.0)
            level_counter[_level_from_score(score)] += 1
    else:
        for sid, score in latest_score_by_student.items():
            _ = sid
            level_counter[_level_from_score(score)] += 1

    # Summary metrics
    avg_score = 0.0
    if latest_score_by_student:
        avg_score = sum(latest_score_by_student.values()) / len(latest_score_by_student)
    avg_progress = 0.0
    if progress_values:
        avg_progress = sum(progress_values) / len(progress_values)

    charts = {
        "study_hours_by_student": [
            {"student_id": sid, "hours": round(hours, 2)}
            for sid, hours in sorted(study_hours.items(), key=lambda x: str(x[0]))
        ],
        "scores_over_time": [
            {"date": date, "avg_score": round(sum(vals) / len(vals), 2)}
            for date, vals in sorted(scores_by_date.items())
            if vals
        ],
        "level_distribution": [
            {"level": level, "count": count} for level, count in sorted(level_counter.items())
        ],
        "topic_mastery_heatmap": topic_mastery_heatmap,
    }

    excel_columns = [
        "student_id",
        "student_name",
        "latest_score",
        "level",
        "study_hours",
        "pre_score",
        "post_score",
        "progress",
        "topic_breakdown",
    ]

    pre_post_by_student = {r.get("student_id"): r for r in pre_vs_post if r.get("student_id") is not None}
    excel_rows: list[dict[str, Any]] = []
    all_student_ids = set(roster_by_id.keys()) | set(latest_score_by_student.keys()) | set(study_hours.keys()) | set(pre_post_by_student.keys())

    for sid in sorted(all_student_ids, key=lambda x: str(x)):
        roster = roster_by_id.get(sid, {})
        pp = pre_post_by_student.get(sid, {})
        latest_score = latest_score_by_student.get(sid, _safe_float(roster.get("score"), 0.0))
        pre_score = _safe_float(pp.get("pre_score"), 0.0)
        post_score = _safe_float(pp.get("post_score"), latest_score)
        progress = post_score - pre_score
        excel_rows.append(
            {
                "student_id": sid,
                "student_name": roster.get("student_name") or roster.get("name") or f"Student {sid}",
                "latest_score": round(latest_score, 2),
                "level": _level_from_score(latest_score),
                "study_hours": round(study_hours.get(sid, 0.0), 2),
                "pre_score": round(pre_score, 2),
                "post_score": round(post_score, 2),
                "progress": round(progress, 2),
                "topic_breakdown": pp.get("topic_scores") or {},
            }
        )

    summary = {
        "class_size": len(class_roster),
        "level_distribution": charts["level_distribution"],
        "average_score": round(avg_score, 2),
        "average_progress": round(avg_progress, 2),
        "top_weak_topics": [topic for topic, _ in weak_topic_counter.most_common(5)],
    }

    narrative = (
        f"Lớp có {summary['class_size']} học sinh, điểm trung bình {summary['average_score']}, "
        f"mức tiến bộ trung bình {summary['average_progress']}. "
        f"Các topic cần ưu tiên: {', '.join(summary['top_weak_topics']) if summary['top_weak_topics'] else 'chưa đủ dữ liệu'}."
    )

    pdf_report_md = "\n".join(
        [
            "# Teacher Analytics Report",
            "",
            f"- Sĩ số: **{summary['class_size']}**",
            f"- Điểm trung bình: **{summary['average_score']}**",
            f"- Tiến bộ trung bình: **{summary['average_progress']}**",
            f"- Top điểm yếu: **{', '.join(summary['top_weak_topics']) if summary['top_weak_topics'] else 'N/A'}**",
            "",
            "## Narrative",
            narrative,
        ]
    )

    return {
        "status": "OK",
        "report": {
            "summary": summary,
            "narrative": narrative,
            "charts": charts,
            "export_payloads": {
                "excel_gradebook": {"columns": excel_columns, "rows": excel_rows},
                "pdf_report_md": pdf_report_md,
            },
        },
    }
