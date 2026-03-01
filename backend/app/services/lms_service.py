from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import statistics

from statistics import mean
from typing import Any

from app.services.llm_service import chat_json, chat_text, llm_available
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlanHomeworkSubmission
from app.models.agent_log import AgentLog
from app.models.diagnostic_attempt import DiagnosticAttempt
from app.models.user import User
from datetime import datetime
from typing import Any

from app.services.bloom import normalize_bloom_level
from app.services.llm_service import chat_text, llm_available
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.document_topic import DocumentTopic
from app.models.learner_profile import LearnerProfile
from app.models.learning_plan import LearningPlan
from app.models.quiz_set import QuizSet
from app.models.student_assignment import StudentAssignment
from app.models.classroom import Classroom, ClassroomMember
from app.models.diagnostic_attempt import DiagnosticAttempt
from app.models.notification import Notification
from app.models.attempt import Attempt
from app.models.classroom_assessment import ClassroomAssessment
from app.core.config import settings
from app.infra.event_bus import RedisEventBus
from app.services.external_sources import fetch_external_snippets


_TEACHER_REPORT_CACHE: dict[int, dict[str, Any]] = {}
_TEACHER_REPORT_CACHE_TTL = timedelta(minutes=30)


@dataclass
class MultiDimProfile:
    primary_level: str
    knowledge_depth: str
    topic_mastery: dict[str, str]
    time_efficiency: str
    consistency: str
    recommended_pace: str


def classify_student_level(total_score: int) -> dict[str, Any]:
    score = max(0, min(100, int(total_score)))
    levels: dict[str, dict[str, Any]] = {
        "gioi": {
            "label": "Giỏi",
            "label_en": "Advanced",
            "min_score": 85,
            "color": "green",
            "emoji": "🌟",
            "description": "Nắm vững kiến thức, sẵn sàng học nội dung nâng cao",
            "learning_approach": "Tập trung vào bài tập khó và bài tập mở rộng",
            "homework_difficulty": "hard",
            "content_level": "advanced",
        },
        "kha": {
            "label": "Khá",
            "label_en": "Intermediate",
            "min_score": 70,
            "color": "blue",
            "emoji": "⭐",
            "description": "Hiểu cơ bản, cần củng cố một số điểm",
            "learning_approach": "Kết hợp ôn tập kiến thức yếu và học mới",
            "homework_difficulty": "medium",
            "content_level": "standard",
        },
        "trung_binh": {
            "label": "Trung Bình",
            "label_en": "Beginner",
            "min_score": 50,
            "color": "orange",
            "emoji": "📚",
            "description": "Cần ôn tập thêm trước khi học nội dung mới",
            "learning_approach": "Tập trung vào kiến thức nền tảng",
            "homework_difficulty": "easy",
            "content_level": "basic",
        },
        "yeu": {
            "label": "Yếu",
            "label_en": "Foundational",
            "min_score": 0,
            "color": "red",
            "emoji": "💪",
            "description": "Cần hỗ trợ thêm – AI sẽ hướng dẫn từng bước",
            "learning_approach": "Học lại từ đầu với hỗ trợ AI intensive",
            "homework_difficulty": "easy",
            "content_level": "remedial",
        },
    }

    for key in ["gioi", "kha", "trung_binh", "yeu"]:
        if score >= int(levels[key]["min_score"]):
            return {"level_key": key, "score": score, **levels[key]}
    return {"level_key": "yeu", "score": score, **levels["yeu"]}


def _safe_percent(value: Any) -> float:
    try:
        return max(0.0, min(100.0, float(value or 0.0)))
    except Exception:
        return 0.0


def _extract_overall_percent(quiz_attempt_result: dict[str, Any] | None) -> float:
    payload = quiz_attempt_result or {}
    overall = payload.get("overall") if isinstance(payload.get("overall"), dict) else {}
    return _safe_percent(
        overall.get("percent")
        or payload.get("overall_percent")
        or payload.get("percent")
        or payload.get("score")
        or payload.get("total_score")
    )


def _extract_topic_percents(quiz_attempt_result: dict[str, Any] | None, document_topics: list[Any] | None) -> dict[str, float]:
    payload = quiz_attempt_result or {}
    by_topic = payload.get("by_topic") if isinstance(payload.get("by_topic"), dict) else {}

    out: dict[str, float] = {}
    for topic, stats in by_topic.items():
        name = str(topic or "").strip()
        if not name:
            continue
        if isinstance(stats, dict):
            total = float(stats.get("total") or 0.0)
            earned = float(stats.get("earned") or 0.0)
            pct = stats.get("percent")
            if pct is None and total > 0:
                pct = (earned / total) * 100.0
            out[name] = _safe_percent(pct)
        else:
            out[name] = _safe_percent(stats)

    for item in document_topics or []:
        if isinstance(item, dict):
            name = str(item.get("topic") or item.get("title") or "").strip()
        else:
            name = str(item or "").strip()
        if name and name not in out:
            out[name] = 0.0

    return out


def _pick_content_chunks_for_topics(
    db: Session,
    *,
    topics: list[str],
    level: str,
    max_chunks: int = 10,
) -> list[dict[str, Any]]:
    reasons = {
        "yeu": "Ôn lại từ gốc để củng cố nền tảng.",
        "trung_binh": "Bù đắp lỗ hổng ở topic dưới 65%.",
        "kha": "Đẩy mạnh nội dung nâng cao và liên hệ mở rộng.",
        "gioi": "Mở rộng ngoài SGK với tài liệu chuyên sâu.",
    }
    selected: list[dict[str, Any]] = []
    max_take = max(1, min(30, int(max_chunks or 10)))

    if db is None:
        return [
            {"chunk_id": -idx, "topic": topic, "reason": reasons.get(level, reasons["trung_binh"])}
            for idx, topic in enumerate(topics[:max_take], start=1)
        ]

    for topic in topics:
        if len(selected) >= max_take:
            break

        topic_obj = db.query(DocumentTopic).filter(DocumentTopic.title.ilike(f"%{topic}%")).order_by(DocumentTopic.created_at.desc()).first()

        if topic_obj and topic_obj.start_chunk_index is not None and topic_obj.end_chunk_index is not None:
            s = min(int(topic_obj.start_chunk_index), int(topic_obj.end_chunk_index))
            e = max(int(topic_obj.start_chunk_index), int(topic_obj.end_chunk_index))
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == int(topic_obj.document_id))
                .filter(DocumentChunk.chunk_index >= s)
                .filter(DocumentChunk.chunk_index <= e)
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(3)
                .all()
            )
        else:
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.text.ilike(f"%{topic}%"))
                .order_by(DocumentChunk.created_at.desc())
                .limit(3)
                .all()
            )

        for c in chunks:
            if len(selected) >= max_take:
                break
            selected.append({"chunk_id": int(c.id), "topic": topic, "reason": reasons.get(level, reasons["trung_binh"])})

    if selected:
        return selected[:max_take]

    for idx, topic in enumerate(topics[:max_take], start=1):
        selected.append({"chunk_id": -idx, "topic": topic, "reason": reasons.get(level, reasons["trung_binh"])})
    return selected


def build_personalized_content_plan(
    db: Session,
    user_id: int,
    quiz_attempt_result: dict[str, Any],
    document_topics: list[str] | list[dict[str, Any]],
) -> dict[str, Any]:
    overall_percent = _extract_overall_percent(quiz_attempt_result)
    student_level_obj = classify_student_level(int(round(overall_percent)))
    student_level = str(student_level_obj["level_key"])

    topic_percents = _extract_topic_percents(quiz_attempt_result, document_topics)
    sorted_topics = sorted(topic_percents.items(), key=lambda x: (x[1], x[0]))
    weak_topics = [topic for topic, pct in sorted_topics if pct < 65.0]

    all_topics = [t for t, _ in sorted_topics] or [str(x if not isinstance(x, dict) else x.get("topic") or x.get("title") or "").strip() for x in (document_topics or [])]
    all_topics = [t for t in all_topics if t]

    teacher_alert = False
    exercise_difficulty_mix = {"easy": 0, "medium": 0, "hard": 0}
    selected_topics: list[str] = []
    personalized_message = ""

    if student_level == "yeu":
        teacher_alert = True
        exercise_difficulty_mix = {"easy": 100, "medium": 0, "hard": 0}
        zero_topics = [t for t, p in sorted_topics if p <= 0.0]
        selected_topics = zero_topics + [t for t in all_topics if t not in zero_topics]
        personalized_message = (
            "Thầy/cô đã mở chế độ học có hướng dẫn cho em. Mỗi 10 phút trợ lý sẽ hỏi thăm tiến độ, "
            "mình sẽ ôn lại từ nền tảng và làm bài mức dễ để chắc kiến thức nhé."
        )
    elif student_level == "trung_binh":
        exercise_difficulty_mix = {"easy": 50, "medium": 50, "hard": 0}
        selected_topics = weak_topics + [t for t in all_topics if t not in weak_topics]
        personalized_message = (
            "Em đang ở mức trung bình tốt. Hệ thống sẽ ưu tiên các topic dưới 65%, "
            "kết hợp bài dễ và trung bình để tăng điểm đều và chắc."
        )
    elif student_level == "kha":
        exercise_difficulty_mix = {"easy": 0, "medium": 40, "hard": 60}
        selected_topics = [t for t, p in sorted_topics if p < 80.0] + [t for t, p in sorted_topics if p >= 80.0]
        personalized_message = (
            "Em đang làm khá tốt. Kế hoạch mới tập trung nội dung nâng cao, "
            "bài đọc mở rộng và tăng tỉ lệ bài khó để bứt phá lên nhóm giỏi."
        )
    else:
        exercise_difficulty_mix = {"easy": 0, "medium": 0, "hard": 100}
        selected_topics = all_topics or weak_topics
        ext = []
        if selected_topics:
            ext = fetch_external_snippets(selected_topics[0], lang="vi", max_sources=1)
        ext_note = f" Nguồn mở rộng gợi ý: {ext[0].get('title')}" if ext else ""
        personalized_message = (
            "Tuyệt vời! Em thuộc nhóm giỏi, hãy tập trung bài HARD, câu hỏi essay và hướng nghiên cứu độc lập."
            f"{ext_note}"
        )

    plan_topics = selected_topics[:8] if selected_topics else weak_topics[:8]
    content_chunks_to_send = _pick_content_chunks_for_topics(db, topics=plan_topics, level=student_level, max_chunks=12)

    return {
        "student_level": student_level,
        "weak_topics": weak_topics,
        "content_chunks_to_send": content_chunks_to_send,
        "exercise_difficulty_mix": exercise_difficulty_mix,
        "personalized_message": personalized_message,
        "teacher_alert": teacher_alert,
    }


def _safe_topic_percentage(value: Any) -> float:
    pct = _safe_percent(value)
    return pct * 100.0 if 0.0 < pct <= 1.0 else pct


def get_student_progress_comparison(user_id: int, classroom_id: int, db: Session) -> dict[str, Any]:
    diagnostic = (
        db.query(DiagnosticAttempt)
        .join(ClassroomAssessment, ClassroomAssessment.assessment_id == DiagnosticAttempt.assessment_id)
        .filter(
            DiagnosticAttempt.user_id == int(user_id),
            ClassroomAssessment.classroom_id == int(classroom_id),
            DiagnosticAttempt.stage == "pre",
        )
        .order_by(DiagnosticAttempt.created_at.asc())
        .first()
    )

    final = (
        db.query(DiagnosticAttempt)
        .join(ClassroomAssessment, ClassroomAssessment.assessment_id == DiagnosticAttempt.assessment_id)
        .filter(
            DiagnosticAttempt.user_id == int(user_id),
            ClassroomAssessment.classroom_id == int(classroom_id),
            DiagnosticAttempt.stage == "post",
        )
        .order_by(DiagnosticAttempt.created_at.desc())
        .first()
    )

    topic_comparison: list[dict[str, Any]] = []
    if diagnostic and final:
        try:
            diag_topics = json.loads(json.dumps((diagnostic.mastery_json or {}).get("by_topic") or {}))
        except Exception:
            diag_topics = {}
        try:
            final_topics = json.loads(json.dumps((final.mastery_json or {}).get("by_topic") or {}))
        except Exception:
            final_topics = {}

        all_topics = sorted(set(diag_topics.keys()) | set(final_topics.keys()))
        for topic in all_topics:
            diag_pct = _safe_topic_percentage(diag_topics.get(topic, 0))
            final_pct = _safe_topic_percentage(final_topics.get(topic, 0))
            topic_comparison.append(
                {
                    "topic": topic,
                    "diagnostic_pct": diag_pct,
                    "final_pct": final_pct,
                    "improvement": final_pct - diag_pct,
                    "improved": final_pct > diag_pct,
                }
            )

    return {
        "diagnostic_score": diagnostic.correct_count if diagnostic else None,
        "diagnostic_pct": diagnostic.score_percent if diagnostic else None,
        "diagnostic_level": diagnostic.level if diagnostic else None,
        "final_score": final.correct_count if final else None,
        "final_pct": final.score_percent if final else None,
        "final_level": final.level if final else None,
        "improvement_points": (final.correct_count - diagnostic.correct_count) if (diagnostic and final) else None,
        "improvement_pct": (final.score_percent - diagnostic.score_percent) if (diagnostic and final) else None,
        "level_changed": (diagnostic.level != final.level) if (diagnostic and final) else False,
        "topic_comparison": topic_comparison,
        "has_final": final is not None,
    }


def _extract_percent(value: Any) -> float:
    if isinstance(value, dict):
        return float(value.get("percent") or value.get("overall_percent") or 0.0)
    return float(value or 0.0)


def _classify_consistency(prev_attempts: list[Any]) -> str:
    values = [_extract_percent(v) for v in (prev_attempts or [])]
    if len(values) < 2:
        return "consistent"
    variance = statistics.pvariance(values)
    delta = values[-1] - values[0]
    if delta <= -10:
        return "declining"
    if variance <= 50:
        return "consistent"
    return "variable"


def classify_student_multidim(
    breakdown: dict[str, Any],
    time_spent_sec: int,
    estimated_time_sec: int,
    prev_attempts: list[Any] | None = None,
) -> MultiDimProfile:
    overall_percent = float(((breakdown or {}).get("overall") or {}).get("percent") or 0.0)
    primary_level = str(classify_student_level(int(round(overall_percent)))["level_key"])

    by_difficulty = (breakdown or {}).get("by_difficulty") or {}
    easy_pct = float((by_difficulty.get("easy") or {}).get("percent") or 0.0)
    medium_pct = float((by_difficulty.get("medium") or {}).get("percent") or 0.0)
    hard_pct = float((by_difficulty.get("hard") or {}).get("percent") or 0.0)

    if hard_pct > 60:
        knowledge_depth = "deep"
    elif medium_pct > 70:
        knowledge_depth = "conceptual"
    elif easy_pct > 85:
        knowledge_depth = "surface"
    else:
        knowledge_depth = "conceptual"

    est = max(1, int(estimated_time_sec or 0))
    spent = max(0, int(time_spent_sec or 0))
    ratio = spent / est
    if ratio < 0.7:
        time_efficiency = "fast"
    elif ratio > 1.4:
        time_efficiency = "slow"
    else:
        time_efficiency = "normal"

    topic_mastery: dict[str, str] = {}
    for topic, stats in ((breakdown or {}).get("by_topic") or {}).items():
        topic_pct = float((stats or {}).get("percent") or 0.0)
        topic_mastery[str(topic)] = str(classify_student_level(int(round(topic_pct)))["level_key"])

    consistency = _classify_consistency(prev_attempts or [])
    weak_topics = [t for t, lvl in topic_mastery.items() if lvl == "yeu"]
    if consistency == "consistent" and knowledge_depth == "deep":
        recommended_pace = "accelerated"
    elif time_efficiency == "slow" or primary_level == "yeu" or weak_topics:
        recommended_pace = "remedial"
    else:
        recommended_pace = "normal"

    return MultiDimProfile(
        primary_level=primary_level,
        knowledge_depth=knowledge_depth,
        topic_mastery=topic_mastery,
        time_efficiency=time_efficiency,
        consistency=consistency,
        recommended_pace=recommended_pace,
    )


def persist_multidim_profile(db: Session, *, user_id: int, profile: MultiDimProfile) -> dict[str, Any]:
    learner = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    if not learner:
        learner = LearnerProfile(user_id=int(user_id), level=profile.primary_level, mastery_json={})
        db.add(learner)

    payload = asdict(profile)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    key = f"multidim_profile_{stamp}"

    mastery = dict(learner.mastery_json or {})
    mastery[key] = payload
    mastery["multidim_profile_latest"] = payload
    learner.level = profile.primary_level
    learner.mastery_json = mastery
    db.commit()
    db.refresh(learner)
    return {"key": key, "profile": payload}


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
    by_topic: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"earned": 0, "total": 0, "bloom_sum": 0.0, "bloom_n": 0})
    by_difficulty: dict[str, dict[str, int]] = defaultdict(
        lambda: {"earned": 0, "total": 0})

    bloom_order = {
        "remember": 1.0,
        "understand": 2.0,
        "apply": 3.0,
        "analyze": 4.0,
        "evaluate": 5.0,
        "create": 6.0,
    }

    total_earned = 0
    total_points = 0
    for item in breakdown or []:
        topic = str(item.get("topic") or "tong_hop").strip().lower()
        max_points = int(item.get("max_points") or 1)
        earned = int(item.get("score_points") or 0)
        earned = max(0, min(max_points, earned))
        difficulty = _difficulty_from_breakdown_item(item)
        bloom = normalize_bloom_level(str(item.get("bloom_level") or "understand"))

        by_topic[topic]["earned"] += earned
        by_topic[topic]["total"] += max_points
        by_topic[topic]["bloom_sum"] += bloom_order.get(bloom, 2.0)
        by_topic[topic]["bloom_n"] += 1

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

    by_topic_out: dict[str, dict[str, float | int | str]] = {}
    bloom_weak_topics: list[dict[str, Any]] = []
    for topic, vals in by_topic.items():
        total = int(vals["total"])
        earned = int(vals["earned"])
        bloom_n = int(vals["bloom_n"])
        bloom_avg = round(float(vals["bloom_sum"]) / max(1, bloom_n), 2)
        percent = round((earned / total) * 100, 2) if total > 0 else 0.0

        if bloom_avg < 2:
            assignment_type = "reading"
            bloom_focus = ["remember", "understand"]
        elif bloom_avg < 3.5:
            assignment_type = "exercise"
            bloom_focus = ["apply", "analyze"]
        else:
            assignment_type = "essay_case_study"
            bloom_focus = ["evaluate", "create"]

        by_topic_out[topic] = {
            "earned": earned,
            "total": total,
            "percent": percent,
            "bloom_avg": bloom_avg,
            "assignment_type": assignment_type,
            "bloom_focus": bloom_focus,
        }
        if percent < 65:
            bloom_weak_topics.append(
                {
                    "topic": topic,
                    "bloom_avg": bloom_avg,
                    "assignment_type": assignment_type,
                    "bloom_focus": bloom_focus,
                    "percent": percent,
                }
            )

    return {
        "overall": {
            "earned": total_earned,
            "total": total_points,
            "percent": round((total_earned / total_points) * 100, 2) if total_points > 0 else 0.0,
        },
        "by_topic": by_topic_out,
        "by_difficulty": _attach_percent(by_difficulty),
        "weak_topics": sorted(bloom_weak_topics, key=lambda x: (x["percent"], x["bloom_avg"])),
    }


def build_recommendations(
    *,
    breakdown: dict[str, Any],
    document_topics: list[str] | None = None,
    multidim_profile: MultiDimProfile | None = None,
) -> list[dict[str, Any]]:
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

    profile = multidim_profile
    if profile and profile.time_efficiency == "fast" and profile.knowledge_depth == "surface":
        recommendations.append(
            {
                "topic": "higher_order_thinking",
                "priority": "high",
                "material": "Bổ sung bài học yêu cầu lập luận và phản biện (evaluate/create).",
                "exercise": "Thực hiện 3 câu evaluate/create để tránh làm nhanh nhưng hời hợt.",
            }
        )

    weak_topic_names = [t for t, lvl in ((profile.topic_mastery if profile else {}) or {}).items() if lvl == "yeu"]
    if profile and profile.time_efficiency == "slow" and weak_topic_names:
        for topic in weak_topic_names[:3]:
            recommendations.append(
                {
                    "topic": topic,
                    "priority": "high",
                    "material": f"Chia nhỏ nội dung chủ đề '{topic}' thành các bước ngắn.",
                    "exercise": f"Giao bài tập từng phần cho '{topic}', hoàn thành tuần tự từ cơ bản đến vận dụng.",
                }
            )

    if profile and profile.consistency == "consistent" and profile.knowledge_depth == "deep":
        recommendations.append(
            {
                "topic": "project_challenge",
                "priority": "normal",
                "material": "Fast-track: giao mini project/challenge liên môn.",
                "exercise": "Hoàn thành một project có phần đánh giá và sáng tạo giải pháp.",
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



def per_student_bloom_analysis(*, by_student_breakdowns: dict[int, list[dict]]) -> list[dict[str, Any]]:
    """Phân tích Bloom theo từng học sinh để giáo viên xem điểm yếu cá nhân."""

    bloom_order = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
    result: list[dict[str, Any]] = []

    for uid, bds in sorted((by_student_breakdowns or {}).items(), key=lambda x: int(x[0])):
        bloom_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"earned": 0, "total": 0})
        topic_scores: dict[str, list[float]] = defaultdict(list)

        for bd in bds or []:
            for topic, vals in (bd.get("by_topic") or {}).items():
                topic_scores[str(topic)].append(float((vals or {}).get("percent") or 0.0))

            # Nếu breakdown gốc không có item-level bloom, fallback dùng topic-level.
            for topic, vals in (bd.get("by_topic") or {}).items():
                bloom = "understand"
                total = int((vals or {}).get("total") or 0)
                earned = int((vals or {}).get("earned") or 0)
                bloom_stats[bloom]["total"] += max(0, total)
                bloom_stats[bloom]["earned"] += max(0, min(total, earned))

        bloom_accuracy = []
        for b in bloom_order:
            earned = int(bloom_stats[b]["earned"])
            total = int(bloom_stats[b]["total"])
            bloom_accuracy.append({
                "bloom_level": b,
                "percent": round((earned / total) * 100, 2) if total > 0 else 0.0,
                "answered": total,
            })

        weak_topics = sorted(
            [
                {"topic": t, "percent": round(sum(vals) / max(1, len(vals)), 2)}
                for t, vals in topic_scores.items()
                if vals and (sum(vals) / len(vals)) < 65
            ],
            key=lambda x: x["percent"],
        )[:5]

        result.append(
            {
                "student_id": int(uid),
                "bloom_accuracy": bloom_accuracy,
                "weak_topics": weak_topics,
            }
        )

    return result
def per_student_bloom_analysis(attempts: list, quiz_kind_map: dict) -> list[dict]:
    """Tính Bloom breakdown và weak topics cho từng học sinh."""

    _ = quiz_kind_map
    bloom_levels = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
    student_data = defaultdict(
        lambda: {
            "bloom": defaultdict(lambda: {"correct": 0, "total": 0}),
            "topics": defaultdict(lambda: {"correct": 0, "total": 0}),
        }
    )

    for at in attempts or []:
        uid = int(at.user_id)
        for item in (at.breakdown_json or []):
            bloom = normalize_bloom_level(str(item.get("bloom_level") or "remember").lower())
            topic = str(item.get("topic") or "unknown")
            correct = bool(item.get("is_correct", False))
            student_data[uid]["bloom"][bloom]["total"] += 1
            if correct:
                student_data[uid]["bloom"][bloom]["correct"] += 1
            student_data[uid]["topics"][topic]["total"] += 1
            if correct:
                student_data[uid]["topics"][topic]["correct"] += 1

    results = []
    for uid, data in sorted(student_data.items()):
        bloom_pct = {
            lvl: round(data["bloom"][lvl]["correct"] / max(1, data["bloom"][lvl]["total"]) * 100, 1)
            for lvl in bloom_levels
        }
        weak_topics = sorted(
            [
                {"topic": t, "accuracy": round(v["correct"] / max(1, v["total"]) * 100, 1)}
                for t, v in data["topics"].items()
            ],
            key=lambda x: x["accuracy"],
        )[:3]
        results.append({"student_id": uid, "bloom_accuracy": bloom_pct, "weak_topics": weak_topics})
    return results


def generate_class_narrative(
    *,
    total_students: int,
    level_dist: dict,
    weak_topics: list[dict],
    avg_improvement: float,
    per_student_data: list[dict] | None = None,
) -> str:
    """Gọi LLM tạo báo cáo tiếng Việt cho GV. Fallback nếu LLM không có."""

    total = max(1, total_students)
    wt = ", ".join(t["topic"] for t in weak_topics[:3]) or "chưa xác định"
    gioi = round(level_dist.get("gioi", 0) / total * 100)
    yeu = round(level_dist.get("yeu", 0) / total * 100)
    imp = f"tăng {abs(avg_improvement):.1f}%" if avg_improvement >= 0 else f"giảm {abs(avg_improvement):.1f}%"
    weakest_students = sorted(
        per_student_data or [],
        key=lambda x: min((x.get("bloom_accuracy") or {"remember": 100}).values() or [100]),
    )[:3]

    weakest_summary = []
    for item in weakest_students:
        bloom_data = item.get("bloom_accuracy") or {}
        if not bloom_data:
            continue
        weakest_level = min(bloom_data, key=bloom_data.get)
        weakest_summary.append(
            f"HS {item.get('student_id')}: {weakest_level} ({float(bloom_data.get(weakest_level) or 0):.1f}%)"
        )
    weakest_summary_text = ", ".join(weakest_summary) or "chưa đủ dữ liệu"

    if not llm_available():
        return (
            f"Lớp có {total_students} học sinh. "
            f"Tỷ lệ giỏi {gioi}%, yếu {yeu}%. "
            f"Điểm trung bình {imp} so với đầu kỳ. "
            f"Cần chú ý các phần: {wt}. "
            f"3 học sinh yếu theo Bloom: {weakest_summary_text}."
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
        f"  Top 3 học sinh yếu nhất theo Bloom: {weakest_summary_text}\n\n"
        "Viết 5-6 câu liền mạch: (1) nhận xét tổng quan, "
        "(2) điểm yếu cụ thể, (3) nhận xét tiến bộ, "
        "(4) nêu rõ Bloom level học sinh còn yếu nhất, "
        "(5) 2 hành động cụ thể cho GV tuần tới."
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


async def generate_class_ai_comment(class_stats: dict) -> str:
    prompt = f"""
    Bạn là AI giáo dục. Dựa trên dữ liệu lớp học sau, hãy viết nhận xét tổng quát
    bằng tiếng Việt (3-5 câu) để gửi cho giáo viên:

    - Tổng học sinh: {class_stats['total_students']}
    - Điểm TB đầu vào: {class_stats['avg_entry']:.1f}
    - Điểm TB cuối kỳ: {class_stats['avg_final']:.1f}
    - Phân loại: {class_stats['distribution']}
    - Topic yếu nhất: {class_stats['weakest_topic']}

    Nhận xét ngắn gọn, tích cực, có định hướng cải thiện.
    """
    if not llm_available():
        return (
            "Lớp học có tiến triển tích cực qua kỳ học. "
            "Giáo viên nên duy trì nhịp ôn tập cho nhóm trung bình/yếu và tăng hoạt động luyện tập theo chủ đề yếu nhất."
        )
    try:
        return await asyncio.to_thread(
            chat_text,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=220,
        )
    except Exception:
        return "Lớp có xu hướng cải thiện, nên tiếp tục hỗ trợ nhóm học sinh còn yếu theo từng chủ đề cụ thể."


def _build_student_ai_evaluation(*, student_data: dict[str, Any]) -> dict[str, Any]:
    fallback = {
        "summary": "Học sinh có tiến bộ nhất định, cần tiếp tục duy trì nhịp học đều đặn.",
        "strengths": ["Hoàn thành được các nội dung trọng tâm"],
        "improvements": ["Tăng cường luyện tập các topic còn yếu", "Duy trì thời lượng học ổn định mỗi tuần"],
        "recommendation": "Theo dõi kết quả theo topic hàng tuần và bổ sung bài tập mục tiêu.",
    }
    if not llm_available():
        return fallback

    system_prompt = (
        "Bạn là giáo viên AI. Hãy viết nhận xét tổng quát ngắn gọn (3-5 câu) về học sinh dựa trên dữ liệu sau. "
        "Nhận xét phải: khách quan, mang tính xây dựng, đề xuất cải thiện cụ thể. "
        "Trả về JSON: {summary: str, strengths: [str], improvements: [str], recommendation: str}"
    )
    try:
        data = chat_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(student_data)},
            ],
            temperature=0.2,
            max_tokens=300,
        )
    except Exception:
        data = {}

    payload = data if isinstance(data, dict) else {}
    return {
        "summary": str(payload.get("summary") or fallback["summary"]).strip(),
        "strengths": [str(x).strip() for x in (payload.get("strengths") or fallback["strengths"]) if str(x).strip()][:5],
        "improvements": [
            str(x).strip() for x in (payload.get("improvements") or fallback["improvements"]) if str(x).strip()
        ][:5],
        "recommendation": str(payload.get("recommendation") or fallback["recommendation"]).strip(),
    }


def _calc_plan_completion(plan: LearningPlan | None, homework_completed: int) -> float:
    if not plan:
        return 0.0
    total_days = max(1, int(getattr(plan, "days_total", 0) or 0))
    return round((max(0, int(homework_completed)) / total_days) * 100.0, 2)


def _topic_scores_from_diag(diag: DiagnosticAttempt | None) -> dict[str, float]:
    if not diag:
        return {}
    mastery = getattr(diag, "mastery_json", {}) or {}
    by_topic = mastery.get("by_topic") if isinstance(mastery.get("by_topic"), dict) else {}
    out: dict[str, float] = {}
    for topic, value in by_topic.items():
        if isinstance(value, dict):
            out[str(topic)] = _safe_percent(value.get("percent") or value.get("score") or 0.0)
        else:
            out[str(topic)] = _safe_percent(value)
    return out


def _extract_topic_scores_for_student(attempt: DiagnosticAttempt | None) -> dict[str, float]:
    if not attempt:
        return {}
    scores = _topic_scores_from_diag(attempt)
    if scores:
        return scores
    try:
        if isinstance(attempt.answers_json, list):
            parsed = score_breakdown(attempt.answers_json).get("by_topic") or {}
            return {str(k): _safe_percent((v or {}).get("percent") or 0.0) for k, v in parsed.items()}
    except Exception:
        return {}
    return {}


def _pick_topics_by_threshold(topic_scores: dict[str, float], *, threshold: float, reverse: bool = False) -> list[str]:
    pairs = sorted(topic_scores.items(), key=lambda x: x[1], reverse=reverse)
    if reverse:
        return [name for name, value in pairs if value >= threshold][:3]
    return [name for name, value in pairs if value < threshold][:3]


def _fallback_evaluation(student: dict[str, Any]) -> dict[str, Any]:
    improvement = student.get("improvement")
    performance = "có tiến bộ" if isinstance(improvement, (int, float)) and improvement > 0 else "cần thêm hỗ trợ"
    return {
        "summary": f"Học sinh {performance} trong giai đoạn vừa qua, cần duy trì lộ trình học ổn định.",
        "strengths": student.get("strong_topics") or ["Duy trì nề nếp học tập"],
        "improvements": student.get("weak_topics") or ["Bổ sung luyện tập chủ đề còn yếu"],
        "recommendation": "Giáo viên theo dõi theo tuần và giao thêm bài tập mục tiêu theo topic.",
        "grade_suggestion": "B",
    }


def _fallback_class_summary(students: list[dict[str, Any]]) -> dict[str, Any]:
    top = [s.get("name") for s in sorted(students, key=lambda x: x.get("final_score") or 0, reverse=True)[:3] if s.get("name")]
    support = [s.get("name") for s in students if (s.get("final_score") or 0) < 50][:5]
    return {
        "overall_assessment": "Lớp học đang có chuyển biến tích cực, cần tiếp tục cá nhân hóa hỗ trợ cho nhóm còn yếu.",
        "class_strengths": ["Nề nếp học tập được duy trì", "Nhiều học sinh có tiến bộ qua kỳ"],
        "class_weaknesses": ["Một số chủ đề nền tảng còn chưa vững"],
        "teacher_recommendations": ["Tăng cường luyện tập theo nhóm chủ đề", "Theo dõi nhóm học sinh cần hỗ trợ hàng tuần"],
        "outstanding_students": top,
        "support_needed": support,
    }


def _generate_student_ai_evaluation(student: dict[str, Any]) -> dict[str, Any]:
    if not llm_available():
        return _fallback_evaluation(student)

    prompt = f"""Bạn là giáo viên kinh nghiệm. Hãy viết nhận xét học sinh.

DỮ LIỆU HỌC SINH:
- Điểm đầu vào: {student.get('diagnostic_score', 'N/A')}%
- Điểm cuối kỳ: {student.get('final_score', 'N/A')}%
- Tiến bộ: {student.get('improvement', 'N/A')}%
- Trình độ: {student.get('level', {}).get('label', 'N/A')}
- Điểm mạnh (topic): {', '.join(student.get('strong_topics', ['N/A']))}
- Điểm yếu (topic): {', '.join(student.get('weak_topics', ['N/A']))}
- Bài tập hoàn thành: {student.get('homework_completed', 0)} bài
- Mức độ hoàn thành lộ trình: {student.get('plan_completion_pct', 0)}%
- Số lần hỏi AI Tutor: {student.get('tutor_sessions', 0)} lần

Viết nhận xét bằng tiếng Việt. Trả về JSON:
{{
  "summary": "Nhận xét tổng quát 2-3 câu",
  "strengths": ["Điểm mạnh 1", "Điểm mạnh 2"],
  "improvements": ["Cần cải thiện 1", "Cần cải thiện 2"],
  "recommendation": "Đề xuất cụ thể cho giáo viên về học sinh này",
  "grade_suggestion": "A/B/C/D/F"
}}"""

    try:
        resp = chat_json(prompt, max_tokens=500, temperature=0.3)
    except Exception:
        resp = None
    return resp if isinstance(resp, dict) else _fallback_evaluation(student)


def _generate_class_ai_summary(students: list[dict[str, Any]]) -> dict[str, Any]:
    if not llm_available() or not students:
        return _fallback_class_summary(students)

    scored = [s for s in students if s.get("final_score") is not None]
    avg_score = sum(float(s["final_score"]) for s in scored) / len(scored) if scored else 0.0
    improvement_values = [float(s["improvement"]) for s in students if isinstance(s.get("improvement"), (int, float))]
    avg_improvement = sum(improvement_values) / len(improvement_values) if improvement_values else 0.0

    level_dist: dict[str, int] = {}
    for s in students:
        lvl = str((s.get("level") or {}).get("label") or "Chưa phân loại")
        level_dist[lvl] = level_dist.get(lvl, 0) + 1

    top_performers = [s.get("name") for s in sorted(students, key=lambda x: x.get("final_score") or 0, reverse=True)[:3] if s.get("name")]
    needs_attention = [s.get("name") for s in students if (s.get("final_score") or 0) < 50 and s.get("name")][:5]

    prompt = f"""Bạn là hiệu trưởng viết báo cáo lớp học. Tiếng Việt.

Dữ liệu lớp:
- Tổng học sinh: {len(students)}
- Điểm TB cuối kỳ: {avg_score:.1f}%
- Cải thiện TB: {avg_improvement:.1f}%
- Phân loại: {level_dist}
- Top 3: {top_performers}
- Cần chú ý: {needs_attention}

Trả về JSON:
{{
  "overall_assessment": "Đánh giá tổng thể lớp (3-4 câu)",
  "class_strengths": ["Điểm mạnh của lớp"],
  "class_weaknesses": ["Điểm cần cải thiện"],
  "teacher_recommendations": ["Gợi ý cho giáo viên (2-3 điểm)"],
  "outstanding_students": ["Tên học sinh xuất sắc"],
  "support_needed": ["Tên học sinh cần hỗ trợ thêm"]
}}"""
    try:
        summary = chat_json(prompt, max_tokens=600, temperature=0.3)
    except Exception:
        summary = None
    return summary if isinstance(summary, dict) else _fallback_class_summary(students)


def generate_full_teacher_report(classroom_id: int, db: Session) -> dict[str, Any]:
    classroom_id = int(classroom_id)
    members = (
        db.query(ClassroomMember)
        .filter(ClassroomMember.classroom_id == classroom_id, ClassroomMember.role == "student")
        .all()
    )

    students_data: list[dict[str, Any]] = []
    for member in members:
        user_id = int(member.user_id)
        diag = (
            db.query(DiagnosticAttempt)
            .filter(DiagnosticAttempt.user_id == user_id, DiagnosticAttempt.stage == "pre")
            .order_by(DiagnosticAttempt.created_at.desc())
            .first()
        )
        final = (
            db.query(DiagnosticAttempt)
            .filter(DiagnosticAttempt.user_id == user_id, DiagnosticAttempt.stage == "post")
            .order_by(DiagnosticAttempt.created_at.desc())
            .first()
        )

        homework_done = (
            db.query(LearningPlanHomeworkSubmission)
            .filter(LearningPlanHomeworkSubmission.user_id == user_id)
            .count()
        )
        plan = (
            db.query(LearningPlan)
            .filter(LearningPlan.user_id == user_id, LearningPlan.classroom_id == classroom_id)
            .order_by(LearningPlan.updated_at.desc())
            .first()
        )
        tutor_queries = db.query(AgentLog).filter(AgentLog.user_id == user_id).count()

        diag_score = float(diag.score_percent) if diag else None
        final_score = float(final.score_percent) if final else None
        topic_scores = _extract_topic_scores_for_student(final or diag)
        base_score = final_score if final_score is not None else (diag_score or 0.0)
        level_key = classify_student_level(int(round(base_score)))
        level_map = {
            "gioi": "Giỏi",
            "kha": "Khá",
            "trung_binh": "Trung bình",
            "yeu": "Yếu",
        }

        student_data = {
            "user_id": user_id,
            "name": str((member.user.full_name if member.user else None) or f"Student #{user_id}"),
            "diagnostic_score": round(diag_score, 2) if diag_score is not None else None,
            "final_score": round(final_score, 2) if final_score is not None else None,
            "improvement": round(final_score - diag_score, 2) if diag_score is not None and final_score is not None else None,
            "level": {"key": level_key, "label": level_map.get(level_key, level_key)},
            "topic_scores": topic_scores,
            "homework_completed": int(homework_done),
            "plan_completion_pct": _calc_plan_completion(plan, homework_done),
            "tutor_sessions": int(tutor_queries),
            "weak_topics": _pick_topics_by_threshold(topic_scores, threshold=60.0, reverse=False),
            "strong_topics": _pick_topics_by_threshold(topic_scores, threshold=75.0, reverse=True),
        }
        student_data["ai_evaluation"] = _generate_student_ai_evaluation(student_data)
        students_data.append(student_data)

    class_summary = _generate_class_ai_summary(students_data)
    classroom = db.get(Classroom, classroom_id)
    return {
        "classroom_id": classroom_id,
        "classroom_name": str(getattr(classroom, "name", None) or f"Classroom #{classroom_id}"),
        "generated_at": datetime.utcnow().isoformat(),
        "total_students": len(students_data),
        "students": students_data,
        "class_summary": class_summary,
        "export_available": True,
    }


def teacher_report(db: Session, classroom_id: int) -> dict[str, Any]:
    classroom_id = int(classroom_id)
    now_dt = datetime.now(timezone.utc)
    cached = _TEACHER_REPORT_CACHE.get(classroom_id)
    if cached:
        generated_at = cached.get("generated_at_dt")
        if isinstance(generated_at, datetime) and (now_dt - generated_at) <= _TEACHER_REPORT_CACHE_TTL:
            return dict(cached.get("report") or {})

    student_ids = [
        int(uid)
        for uid, in db.query(ClassroomMember.user_id).filter(ClassroomMember.classroom_id == classroom_id).all()
    ]
    assessment_ids = [
        int(r[0])
        for r in db.query(ClassroomAssessment.assessment_id)
        .filter(ClassroomAssessment.classroom_id == classroom_id)
        .all()
    ]
    now_iso = now_dt.isoformat()

    if not student_ids:
        return {
            "classroom_id": classroom_id,
            "generated_at": now_iso,
            "summary": {
                "total_students": 0,
                "completed_entry_test": 0,
                "completed_final_exam": 0,
                "average_entry_score": 0.0,
                "average_final_score": 0.0,
                "average_improvement": 0.0,
            },
            "student_list": [],
            "class_analytics": {
                "score_distribution": {"gioi": 0, "kha": 0, "trung_binh": 0, "yeu": 0},
                "topic_performance": {},
                "improvement_chart": [],
            },
            "ai_recommendations": "",
        }

    attempts = (
        db.query(Attempt)
        .filter(Attempt.quiz_set_id.in_(assessment_ids))
        .order_by(Attempt.created_at.asc())
        .all()
        if assessment_ids
        else []
    )
    quiz_kind_map = {
        int(qid): str(kind or "")
        for qid, kind in db.query(QuizSet.id, QuizSet.kind).filter(QuizSet.id.in_(assessment_ids)).all()
    }

    attempts_by_student: dict[int, list[Any]] = defaultdict(list)
    entry_scores: dict[int, float] = {}
    final_scores: dict[int, float] = {}
    latest_breakdown: dict[int, dict[str, Any]] = {}
    chart_bucket: dict[str, list[float]] = defaultdict(list)
    topic_perf_values: dict[str, list[float]] = defaultdict(list)
    topic_perf_students: dict[str, set[int]] = defaultdict(set)

    for at in attempts:
        uid = int(at.user_id)
        if uid not in student_ids:
            continue
        attempts_by_student[uid].append(at)
        breakdown = score_breakdown(at.breakdown_json or [])
        latest_breakdown[uid] = breakdown
        pct = float((breakdown.get("overall") or {}).get("percent") or 0.0)
        chart_bucket[at.created_at.date().isoformat()].append(pct)
        for topic, stats in (breakdown.get("by_topic") or {}).items():
            topic_perf_values[str(topic)].append(float((stats or {}).get("percent") or 0.0))
            topic_perf_students[str(topic)].add(uid)
        kind = quiz_kind_map.get(int(at.quiz_set_id), "")
        if kind == "diagnostic_pre":
            entry_scores[uid] = pct
        elif kind == "diagnostic_post":
            final_scores[uid] = pct

    users = db.query(User).filter(User.id.in_(student_ids)).all()
    user_map = {int(u.id): u for u in users}
    plans = db.query(LearningPlan).filter(LearningPlan.classroom_id == classroom_id).all()
    plan_days_map: dict[int, int] = defaultdict(int)
    for p in plans:
        plan_days_map[int(p.user_id)] = max(plan_days_map[int(p.user_id)], int(p.days_total or 0))
    submissions = (
        db.query(LearningPlanHomeworkSubmission)
        .filter(LearningPlanHomeworkSubmission.user_id.in_(student_ids))
        .all()
    )
    sub_count_by_student: dict[int, int] = defaultdict(int)
    last_submission_by_student: dict[int, datetime] = {}
    for sub in submissions:
        uid = int(sub.user_id)
        sub_count_by_student[uid] += 1
        if sub.created_at and (uid not in last_submission_by_student or sub.created_at > last_submission_by_student[uid]):
            last_submission_by_student[uid] = sub.created_at

    student_list = []
    distribution = {"gioi": 0, "kha": 0, "trung_binh": 0, "yeu": 0}
    for uid in sorted(student_ids):
        entry = entry_scores.get(uid)
        final = final_scores.get(uid)
        base_score = final if final is not None else (entry if entry is not None else 0.0)
        level = classify_student_level(int(round(base_score)))
        level_key = str(level["level_key"])
        distribution[level_key] += 1
        improvement = round((final - entry), 2) if final is not None and entry is not None else None
        if entry is None and final is not None:
            level_change = "new"
        elif improvement is None:
            level_change = "stable"
        elif improvement >= 3:
            level_change = "improved"
        elif improvement <= -3:
            level_change = "declined"
        else:
            level_change = "stable"

        by_topic = (latest_breakdown.get(uid) or {}).get("by_topic") or {}
        sorted_topics = sorted(
            ((str(k), float((v or {}).get("percent") or 0.0)) for k, v in by_topic.items()),
            key=lambda x: x[1],
            reverse=True,
        )
        strong_topics = [k for k, v in sorted_topics if v >= 70][:3]
        weak_topics = [k for k, v in sorted_topics[::-1] if v < 60][:3]

        planned_days = max(1, plan_days_map.get(uid, 0) or sub_count_by_student.get(uid, 0) or 1)
        homework_rate = round((sub_count_by_student.get(uid, 0) / planned_days) * 100, 2)
        duration_values = [float(getattr(at, "duration_sec", 0) or 0) for at in attempts_by_student.get(uid, [])]
        avg_study_time = round(mean(duration_values), 1) if duration_values else 0.0

        topic_scores = {k: round(v, 1) for k, v in sorted_topics}
        ai_evaluation = _build_student_ai_evaluation(
            student_data={
                "name": str((user_map.get(uid).full_name if user_map.get(uid) else None) or f"Student {uid}"),
                "diagnostic_score": round(float(entry or 0.0), 2),
                "final_score": round(float(final or 0.0), 2),
                "topic_scores": topic_scores,
                "completed_exercises": int(sub_count_by_student.get(uid, 0)),
                "avg_study_time_seconds": avg_study_time,
            }
        )

        last_attempt_at = attempts_by_student.get(uid, [])[-1].created_at if attempts_by_student.get(uid) else None
        last_activity = max(x for x in [last_attempt_at, last_submission_by_student.get(uid)] if x is not None) if (last_attempt_at or last_submission_by_student.get(uid)) else None
        user = user_map.get(uid)
        student_list.append(
            {
                "student_id": uid,
                "name": str((user.full_name if user else None) or (user.email if user else None) or f"Student {uid}"),
                "entry_score": round(entry, 2) if entry is not None else None,
                "final_score": round(final, 2) if final is not None else None,
                "improvement": improvement,
                "level": level_key,
                "level_change": level_change,
                "strong_topics": strong_topics,
                "weak_topics": weak_topics,
                "homework_completion_rate": homework_rate,
                "avg_study_time_seconds": avg_study_time,
                "last_activity": last_activity.isoformat() if last_activity else None,
                "ai_evaluation": ai_evaluation,
            }
        )

    top_performers = [x["name"] for x in sorted(student_list, key=lambda s: float(s.get("final_score") or 0.0), reverse=True)[:3]]
    needs_attention = [x["name"] for x in student_list if str(x.get("level") or "") == "yeu"][:5]

    completed_entry = sum(1 for v in entry_scores.values() if v is not None)
    completed_final = sum(1 for v in final_scores.values() if v is not None)
    avg_entry = round(mean(entry_scores.values()), 2) if entry_scores else 0.0
    avg_final = round(mean(final_scores.values()), 2) if final_scores else 0.0
    improvements = [final_scores[uid] - entry_scores[uid] for uid in final_scores if uid in entry_scores]
    avg_improvement = round(mean(improvements), 2) if improvements else 0.0

    topic_performance = {}
    total_students = len(student_ids)
    for topic, values in topic_perf_values.items():
        topic_performance[topic] = {
            "avg_score": round(mean(values), 2),
            "completion_rate": round((len(topic_perf_students[topic]) / max(1, total_students)) * 100, 2),
        }
    weakest_topic = min(topic_performance.items(), key=lambda x: x[1]["avg_score"])[0] if topic_performance else "chưa xác định"

    improvement_chart = [
        {"date": date_str, "avg_score": round(mean(vals), 2)}
        for date_str, vals in sorted(chart_bucket.items(), key=lambda x: x[0])
    ]

    ai_recommendations = asyncio.run(
        generate_class_ai_comment(
            {
                "total_students": total_students,
                "avg_entry": avg_entry,
                "avg_final": avg_final,
                "distribution": distribution,
                "weakest_topic": weakest_topic,
            }
        )
    )

    report = {
        "classroom_id": classroom_id,
        "generated_at": now_iso,
        "students": [
            {
                "user_id": int(s["student_id"]),
                "name": str(s["name"]),
                "diagnostic_score": s["entry_score"],
                "final_score": s["final_score"],
                "improvement_pct": s["improvement"],
                "level": s["level"],
                "topic_scores": {
                    k: round(float((v or {}).get("percent") or 0.0), 1)
                    for k, v in ((latest_breakdown.get(int(s["student_id"])) or {}).get("by_topic") or {}).items()
                },
                "ai_evaluation": s.get("ai_evaluation") or {},
            }
            for s in student_list
        ],
        "class_summary": {
            "avg_improvement": avg_improvement,
            "top_performers": top_performers,
            "needs_attention": needs_attention,
            "overall_assessment": ai_recommendations,
        },
        "summary": {
            "total_students": total_students,
            "completed_entry_test": completed_entry,
            "completed_final_exam": completed_final,
            "average_entry_score": avg_entry,
            "average_final_score": avg_final,
            "average_improvement": avg_improvement,
        },
        "student_list": student_list,
        "class_analytics": {
            "score_distribution": distribution,
            "topic_performance": topic_performance,
            "improvement_chart": improvement_chart,
        },
        "ai_recommendations": ai_recommendations,
    }
    _TEACHER_REPORT_CACHE[classroom_id] = {"generated_at_dt": now_dt, "report": report}
    return report


def _topic_body_len(topic: DocumentTopic) -> int:
    configured = getattr(topic, "body_len", None)
    if configured is not None:
        return int(configured)
    summary = str(getattr(topic, "summary", "") or "")
    return len(summary)


def _topic_chunk_span(topic: DocumentTopic) -> int:
    start = getattr(topic, "start_chunk_index", None)
    end = getattr(topic, "end_chunk_index", None)
    if start is None or end is None:
        return 0
    try:
        return max(0, int(end) - int(start) + 1)
    except Exception:
        return 0


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
    all_topics = query.all()
    if cfg["sort_by_len"]:
        all_topics = sorted(
            all_topics,
            key=lambda t: (
                _topic_chunk_span(t) if _topic_chunk_span(t) > 0 else _topic_body_len(t),
                int(getattr(t, "topic_index", 0) or 0),
                int(getattr(t, "id", 0) or 0),
            ),
        )
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
        plan_json={"assigned_tasks": assigned_tasks, "tasks": assigned_tasks, "student_level": student_level},
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


def _question_prompt_by_assignment_type(assignment_type: str) -> str:
    if assignment_type == "reading":
        return "Tạo câu hỏi mức nhớ/hiểu, ngắn gọn và kiểm tra khái niệm nền tảng."
    if assignment_type == "exercise":
        return "Tạo câu hỏi vận dụng/phân tích, có dữ kiện và yêu cầu lập luận từng bước."
    return "Tạo đề bài essay/case study yêu cầu đánh giá và đề xuất giải pháp."


def _generate_practice_questions(*, topic: str, student_level: str, chunks: list[dict[str, Any]], assignment_type: str) -> list[dict[str, Any]]:
    context = "\n\n".join(str(c.get("text") or "")[:700] for c in chunks[:3])
    if not context.strip():
        context = f"Chủ đề: {topic}"

    if not llm_available():
        return [
            {"question": f"Nêu ý chính của chủ đề '{topic}' từ tài liệu đã đọc.", "bloom": "remember"},
            {"question": f"Giải thích khái niệm quan trọng trong '{topic}' bằng ví dụ ngắn.", "bloom": "understand"},
            {"question": f"Áp dụng kiến thức '{topic}' để xử lý một tình huống đơn giản.", "bloom": "apply"},
        ]

    system = "Bạn là giáo viên tạo bài luyện tập tiếng Việt, trả JSON array 3-5 phần tử."
    user = (
        f"Học sinh level: {student_level}\n"
        f"Topic: {topic}\n"
        f"Loại bài giao: {assignment_type}\n"
        f"Yêu cầu: {_question_prompt_by_assignment_type(assignment_type)}\n"
        "Mỗi phần tử JSON gồm: question, bloom, answer_hint. Không markdown, không text thừa.\n\n"
        f"Ngữ cảnh tài liệu:\n{context}"
    )
    try:
        raw = str(chat_text([{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.2, max_tokens=700) or "")
        import json
        data = json.loads(raw)
        if isinstance(data, list):
            clean = [x for x in data if isinstance(x, dict) and x.get("question")]
            if clean:
                return clean[:5]
    except Exception:
        pass
    return [
        {"question": f"Tóm tắt nội dung chính của chủ đề '{topic}'.", "bloom": "understand"},
        {"question": f"Làm bài luyện tập theo chủ đề '{topic}' theo đúng level {student_level}.", "bloom": "apply"},
        {"question": f"Phân tích lỗi thường gặp khi làm bài về '{topic}'.", "bloom": "analyze"},
    ]


def assign_topic_materials(
    db: Session,
    *,
    student_id: int,
    classroom_id: int,
    student_level: str,
    weak_topics: list[dict[str, Any]] | list[str],
    document_id: int,
) -> list[int]:
    assignment_ids: list[int] = []

    for weak in weak_topics or []:
        if isinstance(weak, dict):
            topic_name = str(weak.get("topic") or "").strip()
            assignment_type = str(weak.get("assignment_type") or "exercise")
            bloom_focus = weak.get("bloom_focus") or []
        else:
            topic_name = str(weak).strip()
            assignment_type = "exercise"
            bloom_focus = []

        if not topic_name:
            continue

        topic_obj = (
            db.query(DocumentTopic)
            .filter(DocumentTopic.document_id == int(document_id))
            .filter(DocumentTopic.title.ilike(f"%{topic_name}%"))
            .first()
        )

        chunk_query = db.query(DocumentChunk).filter(DocumentChunk.document_id == int(document_id))
        if topic_obj and topic_obj.start_chunk_index is not None and topic_obj.end_chunk_index is not None:
            chunk_query = chunk_query.filter(
                DocumentChunk.chunk_index >= int(topic_obj.start_chunk_index),
                DocumentChunk.chunk_index <= int(topic_obj.end_chunk_index),
            )
        else:
            chunk_query = chunk_query.filter(or_(DocumentChunk.text.ilike(f"%{topic_name}%"), DocumentChunk.chunk_index < 8))

        chunks = chunk_query.order_by(DocumentChunk.chunk_index.asc()).limit(5).all()
        chunk_payload = [
            {
                "chunk_id": int(c.id),
                "chunk_index": int(c.chunk_index),
                "text": str(c.text),
                "meta": c.meta if isinstance(c.meta, dict) else {},
            }
            for c in chunks
        ]

        questions = _generate_practice_questions(
            topic=topic_name,
            student_level=student_level,
            chunks=chunk_payload,
            assignment_type=assignment_type,
        )

        row = StudentAssignment(
            student_id=int(student_id),
            classroom_id=int(classroom_id),
            topic_id=int(topic_obj.id) if topic_obj else None,
            document_id=int(document_id),
            assignment_type=assignment_type,
            student_level=str(student_level),
            status="pending",
            content_json={
                "topic": topic_name,
                "bloom_focus": bloom_focus,
                "chunks": chunk_payload,
                "questions": questions,
            },
            due_date=None,
            created_at=datetime.utcnow(),
            completed_at=None,
        )
        db.add(row)
        db.flush()
        assignment_ids.append(int(row.id))

    if assignment_ids:
        db.commit()
    return assignment_ids


def _compact_score_map(score_map: dict[str, Any] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in (score_map or {}).items():
        if isinstance(value, dict):
            out[str(key)] = round(float(value.get("percent") or 0.0), 2)
        else:
            out[str(key)] = round(float(value or 0.0), 2)
    return out


def _mastery_level_from_percent(percent: float) -> str:
    pct = float(percent or 0.0)
    if pct >= 80:
        return "mastered"
    if pct >= 60:
        return "developing"
    return "needs_improvement"


def _topic_name_from_breakdown_item(item: dict[str, Any]) -> str:
    direct = str(item.get("topic") or "").strip()
    if direct:
        return direct
    for src in (item.get("sources") or []):
        meta = src.get("meta") if isinstance(src, dict) else {}
        if not isinstance(meta, dict):
            continue
        for key in ("topic", "topic_title", "title"):
            val = str(meta.get(key) or "").strip()
            if val:
                return val
    return str(item.get("section") or "General").strip() or "General"


def _topic_accuracy_from_breakdown(breakdown: list[dict[str, Any]]) -> dict[str, float]:
    acc: dict[str, dict[str, float]] = {}
    for item in breakdown or []:
        topic = _topic_name_from_breakdown_item(item)
        acc.setdefault(topic, {"score": 0.0, "max": 0.0})
        acc[topic]["score"] += float(item.get("score_points") or 0.0)
        acc[topic]["max"] += float(item.get("max_points") or 0.0)
    return {
        topic: round((vals["score"] / vals["max"]) * 100.0, 1) if vals["max"] > 0 else 0.0
        for topic, vals in acc.items()
    }


def _build_overall_assessment(*, entry_score: float, final_score: float, breakdown: list[dict[str, Any]]) -> str:
    prompt = (
        f"Given entry score {round(entry_score, 1)}%, final score {round(final_score, 1)}%, "
        f"topic breakdown {breakdown}, write a 3-sentence professional assessment in Vietnamese: "
        "sentence 1 = overall progress, sentence 2 = strongest/weakest topics, sentence 3 = recommendation for next steps."
    )
    if llm_available():
        try:
            return str(
                chat_text(
                    [
                        {"role": "system", "content": "Bạn là giáo viên chủ nhiệm đánh giá kết quả cuối kỳ."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=220,
                )
                or ""
            ).strip()
        except Exception:
            pass

    delta = float(final_score or 0.0) - float(entry_score or 0.0)
    progress = "tiến bộ tốt" if delta >= 10 else ("tiến bộ nhẹ" if delta >= 0 else "cần cải thiện thêm")
    strong = [x["topic"] for x in breakdown if float(x.get("final_acc") or 0.0) >= 80][:2]
    weak = [x["topic"] for x in breakdown if float(x.get("final_acc") or 0.0) < 60][:2]
    return (
        f"Học sinh thể hiện {progress} với mức thay đổi {delta:+.1f}% so với điểm đầu vào. "
        f"Các chủ đề mạnh: {', '.join(strong) if strong else 'chưa rõ'}; chủ đề cần củng cố: {', '.join(weak) if weak else 'chưa rõ'}. "
        "Khuyến nghị tiếp tục luyện tập theo các chủ đề yếu và duy trì nhịp ôn tập định kỳ hàng tuần."
    )


def build_student_final_report(
    db: Session,
    *,
    student_id: int,
    quiz_id: int,
    final_score: float,
    final_breakdown: list[dict[str, Any]],
) -> dict[str, Any]:
    student = db.query(User).filter(User.id == int(student_id)).first()
    student_name = str(getattr(student, "full_name", "") or f"User #{student_id}")

    entry_attempt = (
        db.query(Attempt)
        .join(QuizSet, QuizSet.id == Attempt.quiz_set_id)
        .filter(
            Attempt.user_id == int(student_id),
            QuizSet.kind.in_(["entry_test", "diagnostic_pre"]),
        )
        .order_by(Attempt.created_at.desc())
        .first()
    )
    entry_score = float(getattr(entry_attempt, "score_percent", 0.0) or 0.0)
    entry_breakdown = list(getattr(entry_attempt, "breakdown_json", []) or [])

    entry_topic_acc = _topic_accuracy_from_breakdown(entry_breakdown)
    final_topic_acc = _topic_accuracy_from_breakdown(final_breakdown)
    all_topics = sorted(set(entry_topic_acc.keys()) | set(final_topic_acc.keys()))
    topic_breakdown = [
        {
            "topic": topic,
            "entry_acc": round(float(entry_topic_acc.get(topic, 0.0)), 1),
            "final_acc": round(float(final_topic_acc.get(topic, 0.0)), 1),
            "mastery_level": _mastery_level_from_percent(float(final_topic_acc.get(topic, 0.0))),
        }
        for topic in all_topics
    ]
    topic_breakdown.sort(key=lambda x: float(x.get("final_acc") or 0.0), reverse=True)

    weak_topics = [str(row["topic"]) for row in topic_breakdown if float(row["final_acc"]) < 60][:5]
    strong_topics = [str(row["topic"]) for row in topic_breakdown if float(row["final_acc"]) >= 80][:5]
    recommendation = (
        f"Ưu tiên bồi dưỡng các chủ đề yếu: {', '.join(weak_topics)}."
        if weak_topics
        else "Tiếp tục duy trì phong độ và tăng độ khó bài luyện để mở rộng năng lực vận dụng."
    )

    report = {
        "student_name": student_name,
        "entry_score": round(entry_score, 1),
        "final_score": round(float(final_score or 0.0), 1),
        "improvement_delta": round(float(final_score or 0.0) - entry_score, 1),
        "topic_breakdown": topic_breakdown,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "overall_assessment": _build_overall_assessment(
            entry_score=entry_score,
            final_score=float(final_score or 0.0),
            breakdown=topic_breakdown,
        ),
        "recommendation": recommendation,
    }
    return report


def emit_student_final_report_ready(*, student_id: int, report: dict[str, Any]) -> str | None:
    try:
        event_bus = RedisEventBus(settings.REDIS_URL)
        return event_bus.publish(
            event_type="STUDENT_FINAL_REPORT_READY",
            payload=report,
            user_id=str(student_id),
        )
    except Exception:
        return None


def _build_final_exam_report_text(*, student_name: str, subject: str, analytics: dict[str, Any]) -> str:
    total = float((analytics.get("overall") or {}).get("percent") or 0.0)
    by_topic = _compact_score_map(analytics.get("by_topic") or {})
    by_difficulty = _compact_score_map(analytics.get("by_difficulty") or {})

    prompt = (
        f"Tổng hợp năng lực học sinh {student_name} sau bài kiểm tra cuối kỳ môn {subject}:\n"
        f"- Điểm tổng: {round(total, 2)}%\n"
        f"- Điểm theo topic: {by_topic}\n"
        f"- Điểm theo độ khó: {by_difficulty}\n"
        "- Nhận xét tổng quát: [AI tự viết 2-4 câu nhận xét chuyên nghiệp]\n"
        "- Đề xuất: [2-3 điểm cần cải thiện hoặc phát huy]"
    )
    if llm_available():
        try:
            return str(
                chat_text(
                    [
                        {
                            "role": "system",
                            "content": "Bạn là trợ lý học thuật cho giáo viên. Viết báo cáo tiếng Việt ngắn gọn, chuyên nghiệp, có cấu trúc rõ ràng.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=500,
                )
                or ""
            ).strip()
        except Exception:
            pass

    topics = ", ".join(f"{k}: {v}%" for k, v in by_topic.items()) or "chưa có"
    difficulties = ", ".join(f"{k}: {v}%" for k, v in by_difficulty.items()) or "chưa có"
    return (
        f"Học sinh {student_name} hoàn thành bài kiểm tra cuối kỳ môn {subject} với điểm tổng {round(total, 2)}%. "
        f"Theo topic: {topics}. Theo độ khó: {difficulties}. "
        "Nhìn chung, học sinh đã nắm được phần kiến thức trọng tâm, tuy nhiên cần tập trung củng cố các mục có điểm thấp. "
        "Đề xuất: tăng tần suất luyện tập theo topic yếu, bổ sung bài vận dụng mức trung bình-khó, và theo dõi tiến bộ ở lần kiểm tra kế tiếp."
    )


def _send_final_report_to_teacher(
    db: Session,
    *,
    student_id: int,
    quiz_id: int,
    analytics: dict[str, Any],
    breakdown: list[dict[str, Any]],
    report: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> Notification | None:
    student = db.query(User).filter(User.id == int(student_id)).first()
    if not student:
        return None

    membership = db.query(ClassroomMember).filter(ClassroomMember.user_id == int(student_id)).first()
    if not membership:
        return None

    classroom = db.query(Classroom).filter(Classroom.id == int(membership.classroom_id)).first()
    if not classroom:
        return None

    quiz = db.query(QuizSet).filter(QuizSet.id == int(quiz_id)).first()
    subject = str(getattr(quiz, "topic", "Tổng hợp") or "Tổng hợp")
    student_name = str(student.full_name or f"User #{student.id}")
    report_text = _build_final_exam_report_text(student_name=student_name, subject=subject, analytics=analytics or {})

    row = Notification(
        teacher_id=int(classroom.teacher_id),
        student_id=int(student_id),
        quiz_id=int(quiz_id),
        type="student_final_report",
        title=f"Báo cáo cuối kỳ: {student_name}",
        message=report_text,
        payload_json={
            "student": {
                "id": int(student.id),
                "name": student_name,
                "email": str(student.email or ""),
            },
            "quiz_id": int(quiz_id),
            "classroom_id": int(classroom.id),
            "subject": subject,
            "analytics": analytics or {},
            "breakdown": breakdown or [],
            "report": report or {},
            "event": {
                "type": "STUDENT_FINAL_REPORT_READY",
                "id": event_id,
            },
            "created_at": datetime.utcnow().isoformat(),
        },
        is_read=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def push_student_report_to_teacher(
    db: Session,
    *,
    user_id: int,
    quiz_id: int,
    score_percent: float,
    analytics: dict,
) -> None:
    _send_final_report_to_teacher(
        db,
        student_id=int(user_id),
        quiz_id=int(quiz_id),
        analytics=analytics or {"overall": {"percent": float(score_percent or 0.0)}},
        breakdown=[],
    )
