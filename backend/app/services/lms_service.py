from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.llm_service import chat_text, llm_available


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


def generate_class_narrative(
    *,
    total_students: int,
    level_distribution: dict,
    weak_topics: list[dict],
    avg_improvement: float,
) -> str:
    """Gọi LLM tạo báo cáo tiếng Việt cho giáo viên."""

    if not llm_available():
        total = max(1, int(total_students or 0))
        gioi_pct = round(float(level_distribution.get("gioi", 0)) / total * 100)
        yeu_pct = round(float(level_distribution.get("yeu", 0)) / total * 100)
        weak_str = ", ".join([str(t.get("topic") or "") for t in (weak_topics or [])[:3] if t.get("topic")])
        weak_str = weak_str or "chưa xác định"
        return (
            f"Lớp có {int(total_students or 0)} học sinh. "
            f"Tỷ lệ giỏi: {gioi_pct}%, yếu: {yeu_pct}%. "
            f"Các phần cần chú ý: {weak_str}. "
            f"Điểm trung bình {'tăng' if avg_improvement >= 0 else 'giảm'} "
            f"{abs(float(avg_improvement)):.1f}% so với kiểm tra đầu vào."
        )

    total = max(1, int(total_students or 0))
    stats = {
        "total": int(total_students or 0),
        "gioi": f"{level_distribution.get('gioi', 0)} ({round(float(level_distribution.get('gioi', 0)) / total * 100)}%)",
        "kha": f"{level_distribution.get('kha', 0)} ({round(float(level_distribution.get('kha', 0)) / total * 100)}%)",
        "trung_binh": f"{level_distribution.get('trung_binh', 0)} ({round(float(level_distribution.get('trung_binh', 0)) / total * 100)}%)",
        "yeu": f"{level_distribution.get('yeu', 0)} ({round(float(level_distribution.get('yeu', 0)) / total * 100)}%)",
        "weak_topics": [str(t.get("topic") or "") for t in (weak_topics or [])[:3] if t.get("topic")],
        "avg_improvement": f"{'tăng' if avg_improvement >= 0 else 'giảm'} {abs(float(avg_improvement)):.1f}%",
    }

    system = (
        "Bạn là chuyên gia giáo dục cấp cao, có kinh nghiệm phân tích kết quả học tập. "
        "Viết báo cáo nhận xét lớp học CHỈ dựa vào số liệu được cung cấp. "
        "KHÔNG bịa số liệu. KHÔNG dùng từ 'AI', 'hệ thống', 'dữ liệu'. "
        "Viết như giáo viên chủ nhiệm viết nhận xét cuối kỳ: tự nhiên, cụ thể, có tâm."
    )
    user = f"""
Số liệu lớp học:
- Tổng học sinh: {stats['total']}
- Phân loại: Giỏi {stats['gioi']}, Khá {stats['kha']}, TB {stats['trung_binh']}, Yếu {stats['yeu']}
- Tiến bộ so với đầu kỳ: điểm trung bình {stats['avg_improvement']}
- Top 3 phần yếu nhất: {', '.join(stats['weak_topics']) if stats['weak_topics'] else 'Không xác định'}

Hãy viết 5-6 câu báo cáo tiếng Việt gồm:
1. Nhận xét tổng quan kết quả lớp (1-2 câu)
2. Chỉ ra điểm yếu cụ thể cần chú ý (1-2 câu)
3. Nhận xét về sự tiến bộ (1 câu)
4. Đề xuất 2 hành động cụ thể cho giáo viên tuần tới (1-2 câu)
Viết liền mạch, không đánh số, không bullet.
"""

    try:
        result = chat_text(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.3,
            max_tokens=400,
        )
        text = str(result or "").strip()
        return text or "Không thể tạo nhận xét tự động lúc này."
    except Exception:
        return "Không thể tạo nhận xét tự động lúc này."


def analyze_topic_weak_points(attempts_data: list[dict]) -> list[dict]:
    """Phân tích topic yếu nhất của cả lớp từ các kết quả score_breakdown."""

    topic_scores: dict[str, list[float]] = defaultdict(list)

    for bd in attempts_data or []:
        by_topic = (bd or {}).get("by_topic") or {}
        for topic, data in by_topic.items():
            pct = float((data or {}).get("percent") or 0)
            topic_scores[str(topic)].append(pct)

    results: list[dict] = []
    for topic, scores in topic_scores.items():
        avg = sum(scores) / max(1, len(scores))
        weak_count = sum(1 for s in scores if s < 60)

        if avg < 50:
            suggestion = f"Cần ôn tập lại từ đầu, tổ chức buổi học bổ sung cho chủ đề '{topic}'"
        elif avg < 65:
            suggestion = f"Tăng bài tập ứng dụng và ví dụ thực tế cho chủ đề '{topic}'"
        else:
            suggestion = f"Củng cố thêm các dạng bài nâng cao cho chủ đề '{topic}'"

        results.append(
            {
                "topic": topic,
                "avg_score_pct": round(avg, 1),
                "weak_student_count": weak_count,
                "total_student_count": len(scores),
                "weak_ratio_pct": round(weak_count / max(1, len(scores)) * 100, 1),
                "suggestion": suggestion,
            }
        )

    return sorted(results, key=lambda x: (x["avg_score_pct"], x["topic"]))[:10]
