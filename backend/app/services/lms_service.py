from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from app.services.llm_service import chat_json, chat_text, llm_available
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlanHomeworkSubmission
from app.models.user import User
from app.models.document_topic import DocumentTopic
from app.models.learner_profile import LearnerProfile
from app.models.learning_plan import LearningPlan
from app.models.quiz_set import QuizSet


def classify_student_level(total_score: int) -> str:
    score = max(0, min(100, int(total_score)))
    if score >= 85:
        return "gioi"
    if score >= 70:
        return "kha"
    if score >= 50:
        return "trung_binh"
    return "yeu"


def _difficulty_from_breakdown_item(item: dict[str, Any]) -> str:
    bloom = str(item.get("bloom_level") or "").strip().lower()
    qtype = str(item.get("type") or "mcq").strip().lower()
    if qtype == "essay":
        return "hard"
    if bloom in {"remember", "understand"}:
        return "easy"
    if bloom in {"apply", "analyze"}:
        return "medium"
    if bloom:
        return "hard"
    # fallback from points
    max_points = int(item.get("max_points") or 1)
    if max_points <= 1:
        return "easy"
    if max_points <= 3:
        return "medium"
    return "hard"


def score_breakdown(breakdown: list[dict[str, Any]]) -> dict[str, Any]:
    by_topic: dict[str, dict[str, int]] = defaultdict(
        lambda: {"earned": 0, "total": 0})
    by_difficulty: dict[str, dict[str, int]] = defaultdict(
        lambda: {"earned": 0, "total": 0})

    total_earned = 0
    total_points = 0
    for item in breakdown or []:
        topic = str(item.get("topic") or "tong_hop").strip().lower()
        max_points = int(item.get("max_points") or 1)
        earned = int(item.get("score_points") or 0)
        earned = max(0, min(max_points, earned))
        difficulty = _difficulty_from_breakdown_item(item)

        by_topic[topic]["earned"] += earned
        by_topic[topic]["total"] += max_points
        by_difficulty[difficulty]["earned"] += earned
        by_difficulty[difficulty]["total"] += max_points
        total_earned += earned
        total_points += max_points

    def _attach_percent(bucket: dict[str, dict[str, int]]) -> dict[str, dict[str, float | int]]:
        out: dict[str, dict[str, float | int]] = {}
        for k, v in bucket.items():
            total = int(v["total"])
            earned = int(v["earned"])
            out[k] = {
                "earned": earned,
                "total": total,
                "percent": round((earned / total) * 100, 2) if total > 0 else 0.0,
            }
        return out

    return {
        "overall": {
            "earned": total_earned,
            "total": total_points,
            "percent": round((total_earned / total_points) * 100, 2) if total_points > 0 else 0.0,
        },
        "by_topic": _attach_percent(by_topic),
        "by_difficulty": _attach_percent(by_difficulty),
    }


def build_recommendations(*, breakdown: dict[str, Any], document_topics: list[str] | None = None) -> list[dict[str, Any]]:
    topic_scores = breakdown.get("by_topic") or {}
    weak_topics = [k for k, v in topic_scores.items() if float(
        (v or {}).get("percent") or 0) < 65]
    recommendations: list[dict[str, Any]] = []
    all_topics = document_topics or []

    for topic in weak_topics[:6]:
        recommendations.append(
            {
                "topic": topic,
                "priority": "high",
                "material": f"Ôn lại lý thuyết trọng tâm chủ đề '{topic}'",
                "exercise": f"Làm bộ bài tập củng cố cho chủ đề '{topic}' (10 câu: dễ→khó)",
            }
        )

    if not recommendations and all_topics:
        for topic in all_topics[:3]:
            recommendations.append(
                {
                    "topic": topic,
                    "priority": "normal",
                    "material": f"Tiếp tục mở rộng kiến thức ở '{topic}'",
                    "exercise": f"Bài tập nâng cao theo chủ đề '{topic}'",
                }
            )

    return recommendations


def analyze_topic_weak_points(all_breakdowns: list[dict]) -> list[dict]:
    """Tổng hợp topic nào cả lớp đang yếu nhất."""

    topic_pcts: dict[str, list[float]] = defaultdict(list)
    for bd in all_breakdowns or []:
        for topic, data in (bd.get("by_topic") or {}).items():
            topic_pcts[topic].append(float((data or {}).get("percent") or 0))

    result: list[dict[str, Any]] = []
    for topic, pcts in topic_pcts.items():
        avg = sum(pcts) / max(1, len(pcts))
        weak_n = sum(1 for p in pcts if p < 60)
        if avg < 50:
            sug = f"Cần dạy lại từ đầu, tổ chức buổi phụ đạo riêng cho '{topic}'"
        elif avg < 65:
            sug = f"Tăng bài tập ứng dụng và ví dụ thực tế cho '{topic}'"
        else:
            sug = f"Củng cố thêm dạng bài nâng cao cho '{topic}'"
        result.append(
            {
                "topic": topic,
                "avg_pct": round(avg, 1),
                "weak_count": weak_n,
                "total": len(pcts),
                "suggestion": sug,
            }
        )
    return sorted(result, key=lambda x: x["avg_pct"])[:10]


def generate_class_narrative(
    *,
    total_students: int,
    level_dist: dict,
    weak_topics: list[dict],
    avg_improvement: float,
) -> str:
    """Gọi LLM tạo báo cáo tiếng Việt cho GV. Fallback nếu LLM không có."""

    total = max(1, total_students)
    wt = ", ".join(t["topic"] for t in weak_topics[:3]) or "chưa xác định"
    gioi = round(level_dist.get("gioi", 0) / total * 100)
    yeu = round(level_dist.get("yeu", 0) / total * 100)
    imp = f"tăng {abs(avg_improvement):.1f}%" if avg_improvement >= 0 else f"giảm {abs(avg_improvement):.1f}%"

    if not llm_available():
        return (
            f"Lớp có {total_students} học sinh. "
            f"Tỷ lệ giỏi {gioi}%, yếu {yeu}%. "
            f"Điểm trung bình {imp} so với đầu kỳ. "
            f"Cần chú ý các phần: {wt}."
        )

    system = (
        "Bạn là chuyên gia giáo dục. Viết báo cáo ngắn gọn bằng tiếng Việt cho GV. "
        "CHỈ dùng số liệu được cung cấp. Không bịa. "
        "Không dùng từ AI/hệ thống. Viết tự nhiên, có tâm."
    )
    user = (
        f"Lớp {total_students} học sinh:\n"
        f"  Giỏi: {level_dist.get('gioi', 0)} ({gioi}%), "
        f"  Khá: {level_dist.get('kha', 0)}, "
        f"  TB: {level_dist.get('trung_binh', 0)}, "
        f"  Yếu: {level_dist.get('yeu', 0)} ({yeu}%)\n"
        f"  Tiến bộ so với đầu kỳ: điểm TB {imp}\n"
        f"  Top 3 phần yếu: {wt}\n\n"
        "Viết 5-6 câu liền mạch: (1) nhận xét tổng quan, "
        "(2) điểm yếu cụ thể, (3) nhận xét tiến bộ, "
        "(4) 2 hành động cụ thể cho GV tuần tới."
    )
    try:
        return str(
            chat_text(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.3,
                max_tokens=350,
            )
            or ""
        ).strip()
    except Exception:
        return f"Lớp {total_students} HS, điểm TB {imp}. Cần chú ý: {wt}."


def generate_student_evaluation_report(
    student_id: int,
    pre_attempt: dict,
    post_attempt: dict,
    homework_results: list[dict],
    db: Session,
) -> dict:
    """Tạo báo cáo đánh giá chi tiết cho 1 học sinh bằng LLM (kèm fallback cứng)."""

    _ = db  # giữ chữ ký để có thể mở rộng truy vấn DB trong tương lai

    pre_score = float((pre_attempt or {}).get("overall", {}).get("percent") or 0.0)
    post_score = float((post_attempt or {}).get("overall", {}).get("percent") or 0.0)
    delta = post_score - pre_score

    post_topics = (post_attempt or {}).get("by_topic") or {}
    topic_lines = []
    for topic, info in sorted(post_topics.items(), key=lambda x: float((x[1] or {}).get("percent") or 0), reverse=True):
        topic_lines.append(f"- {topic}: {float((info or {}).get('percent') or 0):.1f}%")
    topic_breakdown = "\n".join(topic_lines) if topic_lines else "- Chưa có dữ liệu topic"

    by_diff = (post_attempt or {}).get("by_difficulty") or {}
    easy_percent = float((by_diff.get("easy") or {}).get("percent") or 0.0)
    medium_percent = float((by_diff.get("medium") or {}).get("percent") or 0.0)
    hard_percent = float((by_diff.get("hard") or {}).get("percent") or 0.0)

    total_hw = len(homework_results or [])
    completed_hw = sum(1 for x in (homework_results or []) if bool((x or {}).get("completed", True)))
    hw_scores = [float((x or {}).get("score") or (x or {}).get("score_percent") or 0.0) for x in (homework_results or [])]
    homework_completion_rate = round((completed_hw / total_hw) * 100, 1) if total_hw > 0 else 0.0
    homework_avg = round(mean(hw_scores), 1) if hw_scores else 0.0

    progress_label = "ổn định"
    if delta >= 12:
        progress_label = "tiến bộ rõ rệt"
    elif delta < -5:
        progress_label = "sụt giảm"
    elif delta < 2:
        progress_label = "chưa cải thiện"

    def _fallback_grade(score: float) -> str:
        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        if score >= 40:
            return "D"
        return "F"

    sorted_topics = sorted(post_topics.items(), key=lambda x: float((x[1] or {}).get("percent") or 0), reverse=True)
    strengths = [t for t, info in sorted_topics if float((info or {}).get("percent") or 0) >= 70][:3]
    weaknesses = [t for t, info in sorted_topics[::-1] if float((info or {}).get("percent") or 0) < 60][:3]

    if not llm_available():
        return {
            "student_id": int(student_id),
            "overall_grade": _fallback_grade(post_score),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "progress": progress_label,
            "improvement_delta": round(delta, 1),
            "recommendation_for_teacher": "Theo dõi sát các topic yếu, giao thêm bài tập theo mức độ và phản hồi cá nhân mỗi tuần.",
            "ai_comment": (
                f"Học sinh có điểm đầu vào {pre_score:.1f}% và điểm cuối kỳ {post_score:.1f}%, mức thay đổi {delta:+.1f}%. "
                f"Các điểm mạnh hiện tại: {', '.join(strengths) if strengths else 'chưa nổi bật rõ'}. "
                f"Cần ưu tiên cải thiện: {', '.join(weaknesses) if weaknesses else 'chưa xác định cụ thể'}. "
                "Giáo viên nên duy trì nhịp luyện tập đều và theo dõi tiến độ theo từng tuần."
            ),
        }

    system = "Bạn là giáo viên AI chuyên đánh giá học sinh. Luôn trả về JSON hợp lệ, không markdown, không giải thích thêm."
    user = (
        "Dựa trên dữ liệu sau, hãy viết đánh giá học sinh bằng tiếng Việt:\n"
        f"Điểm kiểm tra đầu vào: {pre_score:.1f}% | Điểm cuối kỳ: {post_score:.1f}%\n"
        f"Tiến bộ: {delta:+.1f}%\n"
        f"Điểm theo topic (cuối kỳ):\n{topic_breakdown}\n"
        "Điểm theo độ khó:\n"
        f"Dễ: {easy_percent:.1f}% | Trung bình: {medium_percent:.1f}% | Khó: {hard_percent:.1f}%\n\n"
        f"Kết quả bài tập: {homework_completion_rate:.1f}% hoàn thành, điểm TB {homework_avg:.1f}%\n"
        "Hãy trả về JSON với cấu trúc:\n"
        "{\n"
        '"overall_grade": "A/B/C/D/F",\n'
        '"strengths": ["topic mạnh 1", "topic mạnh 2"],\n'
        '"weaknesses": ["topic yếu 1", "topic yếu 2"],\n'
        '"progress": "tiến bộ rõ rệt|ổn định|chưa cải thiện|sụt giảm",\n'
        '"recommendation_for_teacher": "...",\n'
        '"ai_comment": "Học sinh ... [nhận xét 3-5 câu bằng tiếng Việt tự nhiên]"\n'
        "}"
    )
    try:
        report = chat_json(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=600,
        )
    except Exception:
        report = {}

    return {
        "student_id": int(student_id),
        "overall_grade": str(report.get("overall_grade") or _fallback_grade(post_score)).strip().upper()[:1],
        "strengths": [str(x).strip() for x in (report.get("strengths") or strengths) if str(x).strip()][:5],
        "weaknesses": [str(x).strip() for x in (report.get("weaknesses") or weaknesses) if str(x).strip()][:5],
        "progress": str(report.get("progress") or progress_label).strip().lower(),
        "improvement_delta": round(delta, 1),
        "recommendation_for_teacher": str(
            report.get("recommendation_for_teacher")
            or "Ưu tiên hỗ trợ các lỗ hổng kiến thức và giao bài tập phân hóa theo từng mảng nội dung."
        ).strip(),
        "ai_comment": str(report.get("ai_comment") or "").strip()
        or (
            f"Học sinh cải thiện {delta:+.1f}% so với đầu kỳ. "
            f"Điểm cuối kỳ đạt {post_score:.1f}%. "
            "Cần tiếp tục luyện tập đều và tập trung vào các topic còn yếu để nâng độ vững kiến thức."
        ),
    }


def get_student_homework_results(student_id: int, db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(LearningPlanHomeworkSubmission)
        .filter(LearningPlanHomeworkSubmission.user_id == int(student_id))
        .order_by(LearningPlanHomeworkSubmission.created_at.asc())
        .all()
    )
    results: list[dict[str, Any]] = []
    for r in rows:
        grade = r.grade_json or {}
        score = float(grade.get("score") or grade.get("score_percent") or 0.0)
        results.append(
            {
                "submission_id": int(r.id),
                "completed": True,
                "score": score,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
            }
        )
    return results


def resolve_student_name(student_id: int, db: Session) -> str:
    user = db.query(User).filter(User.id == int(student_id)).first()
    if not user:
        return f"Student {student_id}"
    return str(user.full_name or user.email or f"Student {student_id}")


def _topic_body_len(topic: DocumentTopic) -> int:
    configured = getattr(topic, "body_len", None)
    if configured is not None:
        return int(configured)
    summary = str(getattr(topic, "summary", "") or "")
    return len(summary)


def assign_learning_path(
    db: Session,
    *,
    user_id: int,
    student_level: str,
    document_ids: list[int],
    classroom_id: int = 0,
) -> dict[str, Any]:
    """Gán topics + quizzes theo level, lưu vào LearnerProfile + LearningPlan."""

    level_cfg = {
        "yeu": {"max_topics": 3, "sort_by_len": True, "quiz_level": "beginner"},
        "trung_binh": {"max_topics": 5, "sort_by_len": False, "quiz_level": "intermediate"},
        "kha": {"max_topics": 7, "sort_by_len": False, "quiz_level": "intermediate"},
        "gioi": {"max_topics": 20, "sort_by_len": False, "quiz_level": "advanced"},
    }
    cfg = level_cfg.get(student_level, level_cfg["trung_binh"])

    query = db.query(DocumentTopic).filter(
        DocumentTopic.document_id.in_([int(doc_id) for doc_id in (document_ids or [])])
    )
    if cfg["sort_by_len"]:
        query = query.order_by(DocumentTopic.body_len.asc().nullslast())
    all_topics = query.all()
    selected = all_topics[: int(cfg["max_topics"])]

    reasons = {
        "yeu": "Nội dung cơ bản — xây nền tảng vững chắc",
        "trung_binh": "Nội dung vừa sức — củng cố và mở rộng",
        "kha": "Nội dung nâng cao — phát triển tư duy sâu hơn",
        "gioi": "Toàn bộ nội dung + thách thức chuyên sâu",
    }

    assigned_tasks: list[dict[str, Any]] = []
    for topic in selected:
        quiz = (
            db.query(QuizSet)
            .filter(
                QuizSet.level == str(cfg["quiz_level"]),
                QuizSet.kind.in_(["practice", "quiz", "assessment"]),
            )
            .filter(QuizSet.topic.ilike(f"%{str(topic.title or '')[:20]}%"))
            .first()
        ) or db.query(QuizSet).filter(QuizSet.level == str(cfg["quiz_level"])).first()

        assigned_tasks.append(
            {
                "topic_id": int(topic.id),
                "topic_title": str(topic.title),
                "document_id": int(topic.document_id),
                "quiz_id": int(quiz.id) if quiz else None,
                "quiz_level": str(cfg["quiz_level"]),
                "status": "pending",
                "reason": reasons.get(student_level, ""),
            }
        )

    profile = db.query(LearnerProfile).filter(
        LearnerProfile.user_id == int(user_id)).first()
    if profile:
        profile.level = student_level
    else:
        profile = LearnerProfile(user_id=int(
            user_id), level=student_level, mastery_json={})
        db.add(profile)

    plan = LearningPlan(
        user_id=int(user_id),
        classroom_id=int(classroom_id or 0),
        level=student_level,
        plan_json={"assigned_tasks": assigned_tasks, "student_level": student_level},
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return {
        "plan_id": int(plan.id),
        "student_level": student_level,
        "assigned_topics": [
            {
                "id": t["topic_id"],
                "title": t["topic_title"],
                "document_id": t["document_id"],
                "reason": t["reason"],
            }
            for t in assigned_tasks
        ],
        "assigned_quizzes": [
            {"quiz_id": t["quiz_id"], "topic": t["topic_title"],
                "level": t["quiz_level"]}
            for t in assigned_tasks
            if t["quiz_id"]
        ],
        "total_assigned": len(assigned_tasks),
    }
