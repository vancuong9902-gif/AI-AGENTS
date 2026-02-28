from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import statistics

from statistics import mean
from typing import Any

from app.services.llm_service import chat_json, chat_text, llm_available
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlanHomeworkSubmission
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
from app.models.notification import Notification


@dataclass
class MultiDimProfile:
    primary_level: str
    knowledge_depth: str
    topic_mastery: dict[str, str]
    time_efficiency: str
    consistency: str
    recommended_pace: str


def classify_student_level(total_score: int) -> str:
    score = max(0, min(100, int(total_score)))
    if score >= 85:
        return "gioi"
    if score >= 70:
        return "kha"
    if score >= 50:
        return "trung_binh"
    return "yeu"


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
    primary_level = classify_student_level(int(round(overall_percent)))

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
        topic_mastery[str(topic)] = classify_student_level(int(round(topic_pct)))

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
