from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

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
    by_topic: dict[str, dict[str, int]] = defaultdict(lambda: {"earned": 0, "total": 0})
    by_difficulty: dict[str, dict[str, int]] = defaultdict(lambda: {"earned": 0, "total": 0})

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
    weak_topics = [k for k, v in topic_scores.items() if float((v or {}).get("percent") or 0) < 65]
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
    classroom_id: int,
) -> dict[str, Any]:
    """Auto-assigns topic + quiz by learner level and persists profile + learning path."""
    all_topics = (
        db.query(DocumentTopic)
        .filter(DocumentTopic.document_id.in_([int(doc_id) for doc_id in (document_ids or [])]))
        .order_by(DocumentTopic.id)
        .all()
    )

    level_config = {
        "yeu": {"max_topics": 3, "prefer_short": True, "max_body_len": 2500},
        "trung_binh": {"max_topics": 5, "prefer_short": False, "max_body_len": 5000},
        "kha": {"max_topics": 7, "prefer_short": False, "max_body_len": 99999},
        "gioi": {"max_topics": 99, "prefer_short": False, "max_body_len": 99999},
    }
    cfg = level_config.get(student_level, level_config["trung_binh"])

    sorted_topics = sorted(all_topics, key=_topic_body_len) if cfg["prefer_short"] else all_topics
    selected_topics = [t for t in sorted_topics if _topic_body_len(t) <= int(cfg["max_body_len"])][: int(cfg["max_topics"])]

    quiz_level_map = {
        "yeu": "beginner",
        "trung_binh": "intermediate",
        "kha": "intermediate",
        "gioi": "advanced",
    }
    q_level = quiz_level_map.get(student_level, "intermediate")

    reason_map = {
        "yeu": "Nội dung cơ bản, phù hợp để xây dựng nền tảng",
        "trung_binh": "Nội dung vừa sức, giúp củng cố và mở rộng",
        "kha": "Nội dung nâng cao, phát triển tư duy sâu hơn",
        "gioi": "Nội dung chuyên sâu, thách thức và mở rộng toàn diện",
    }

    assigned_tasks: list[dict[str, Any]] = []
    for topic in selected_topics:
        quiz = (
            db.query(QuizSet)
            .filter(
                QuizSet.topic.ilike(f"%{str(topic.title or '')[:30]}%"),
                QuizSet.level == q_level,
                QuizSet.kind.in_(["practice", "quiz"]),
            )
            .first()
        )
        if not quiz:
            quiz = db.query(QuizSet).filter(QuizSet.level == q_level).first()

        assigned_tasks.append(
            {
                "topic_id": int(topic.id),
                "topic_title": str(topic.title),
                "document_id": int(topic.document_id),
                "quiz_id": int(quiz.id) if quiz else None,
                "quiz_level": q_level,
                "status": "pending",
                "recommended_reason": reason_map.get(student_level, ""),
            }
        )

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    if profile:
        profile.level = student_level
    else:
        profile = LearnerProfile(user_id=int(user_id), level=student_level, mastery_json={})
        db.add(profile)

    plan = LearningPlan(
        user_id=int(user_id),
        classroom_id=int(classroom_id),
        level=student_level,
        plan_json={"tasks": assigned_tasks},
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
                "reason": t["recommended_reason"],
            }
            for t in assigned_tasks
        ],
        "assigned_quizzes": [
            {"quiz_id": t["quiz_id"], "topic": t["topic_title"], "level": t["quiz_level"]}
            for t in assigned_tasks
            if t["quiz_id"]
        ],
        "total_assigned": len(assigned_tasks),
    }
