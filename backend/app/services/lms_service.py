from __future__ import annotations

from collections import defaultdict
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
