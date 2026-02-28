from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List


_TOPIC_RE = re.compile(r"chủ\s*đề\s*['\"\“\”]([^'\"\“\”]+)['\"\“\”]", re.IGNORECASE)


def _infer_topic_from_stem(stem: str) -> str:
    """Try to infer a topic label from our enforced stem convention.

    We prefer stems like: Chủ đề 'sql': ...
    """
    m = _TOPIC_RE.search(stem or "")
    if m:
        return m.group(1).strip().lower()
    return "(unknown)"


def analyze_assessment(assessment: Dict[str, Any], *, kind: str = "") -> Dict[str, Any]:
    """Compute light-weight analytics for an assessment dict.

    Input is compatible with assessment_service.get_assessment output.
    """
    questions: List[Dict[str, Any]] = assessment.get("questions") or []

    by_type = Counter()
    by_bloom = Counter()
    by_topic = Counter()

    estimated_points = 0
    notes: List[str] = []

    for q in questions:
        qtype = str(q.get("type") or "").lower() or "unknown"
        by_type[qtype] += 1

        bloom = str(q.get("bloom_level") or "").lower() or "(unknown)"
        by_bloom[bloom] += 1

        stem = str(q.get("stem") or "")
        by_topic[_infer_topic_from_stem(stem)] += 1

        if qtype == "mcq":
            estimated_points += 1
        elif qtype == "essay":
            try:
                estimated_points += int(q.get("max_points") or 0)
            except Exception:
                pass

    if by_topic.get("(unknown)"):
        notes.append("Một số câu không có nhãn chủ đề trong stem (khuyến nghị chuẩn hoá: Chủ đề '...': ...).")
    if kind == "diagnostic_pre" and by_type.get("essay", 0) < 1:
        notes.append("Bài đầu vào nên có ít nhất 1 câu tự luận để đo năng lực vận dụng/diễn giải.")
    if by_type.get("mcq", 0) and by_bloom.get("remember", 0) == 0:
        notes.append("MCQ chưa có câu mức nhớ (remember) — cân nhắc thêm 1–2 câu khởi động.")

    return {
        "assessment_id": assessment.get("assessment_id"),
        "title": assessment.get("title"),
        "level": assessment.get("level"),
        "kind": kind,
        "question_count": len(questions),
        "by_type": dict(by_type),
        "by_bloom": dict(by_bloom),
        "by_topic": dict(by_topic),
        "estimated_points": int(estimated_points),
        "notes": notes,
    }
