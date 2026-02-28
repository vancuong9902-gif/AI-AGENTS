from __future__ import annotations

from typing import Any
import re


_WORD_RX = re.compile(r"[A-Za-zÀ-ỹ0-9_]+", flags=re.UNICODE)


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _extract_answer(student_answers: Any, question_id: Any) -> Any:
    qid = str(question_id)
    if isinstance(student_answers, dict):
        if qid in student_answers:
            return student_answers[qid]
        if question_id in student_answers:
            return student_answers[question_id]

    if isinstance(student_answers, list):
        for item in student_answers:
            if not isinstance(item, dict):
                continue
            if str(item.get("question_id")) == qid:
                if "answer" in item:
                    return item.get("answer")
                if "response" in item:
                    return item.get("response")
    return None


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RX.findall(text or "") if len(t) >= 3]


def _build_evidence_index(evidence_chunks: Any) -> dict[str, str]:
    out: dict[str, list[str]] = {}

    if isinstance(evidence_chunks, dict):
        for source, chunks in evidence_chunks.items():
            texts: list[str] = []
            if isinstance(chunks, list):
                for c in chunks:
                    if isinstance(c, dict):
                        txt = c.get("text") or c.get("content") or ""
                    else:
                        txt = str(c)
                    if txt:
                        texts.append(str(txt))
            elif isinstance(chunks, str):
                texts.append(chunks)
            out[str(source)] = texts
    elif isinstance(evidence_chunks, list):
        for ch in evidence_chunks:
            if not isinstance(ch, dict):
                continue
            source = str(ch.get("source") or ch.get("source_id") or "global")
            txt = str(ch.get("text") or ch.get("content") or "")
            if txt:
                out.setdefault(source, []).append(txt)

    return {k: "\n".join(v) for k, v in out.items()}


def _question_evidence_text(question: dict[str, Any], evidence_index: dict[str, str]) -> str:
    sources = question.get("sources") or []
    if not isinstance(sources, list):
        sources = [sources]
    parts: list[str] = []
    for s in sources:
        key = str(s)
        if key in evidence_index:
            parts.append(evidence_index[key])
    if not parts and "global" in evidence_index:
        parts.append(evidence_index["global"])
    return "\n".join(parts)


def _score_essay_with_rubric(question: dict[str, Any], student_answer: Any, evidence_text: str) -> tuple[int, int, str]:
    rubric = question.get("rubric") or []
    answer_text = str(student_answer or "")
    answer_norm = answer_text.lower()
    max_points = _to_int(question.get("max_points"), 0)
    if max_points <= 0:
        max_points = sum(_to_int(r.get("points"), 0) for r in rubric if isinstance(r, dict)) or 1

    if not isinstance(rubric, list) or not rubric:
        return 0, max_points, "Không có rubric hợp lệ để chấm."

    earned = 0.0
    notes: list[str] = []
    outside_count = 0
    for idx, criterion in enumerate(rubric, start=1):
        if not isinstance(criterion, dict):
            continue
        c_points = float(_to_int(criterion.get("points"), 0))
        if c_points <= 0:
            continue

        kws = criterion.get("keywords") or criterion.get("key_terms") or []
        if isinstance(kws, str):
            kws = [kws]
        kws = [str(k).strip().lower() for k in kws if str(k).strip()]

        if not kws:
            expected = criterion.get("expected") or criterion.get("model_answer") or ""
            kws = _tokenize(str(expected))[:6]

        if not kws:
            notes.append(f"Tiêu chí {idx}: thiếu từ khóa nên không thể cộng điểm.")
            continue

        in_answer = [k for k in kws if re.search(rf"\b{re.escape(k)}\b", answer_norm)]
        in_evidence = [k for k in kws if re.search(rf"\b{re.escape(k)}\b", evidence_text.lower())]
        supported = [k for k in in_answer if k in in_evidence]
        unsupported = [k for k in in_answer if k not in in_evidence]

        if unsupported:
            outside_count += len(unsupported)

        ratio = float(len(supported)) / float(max(1, len(kws)))
        earned_part = c_points * ratio
        earned += earned_part
        notes.append(f"Tiêu chí {idx}: {earned_part:.2f}/{c_points:.0f} điểm.")

    earned_int = max(0, min(max_points, int(round(earned))))
    comment = " ".join(notes)
    if outside_count > 0:
        comment = f"{comment} Có ý đúng nhưng ngoài tài liệu (không có trong evidence_chunks) nên không cộng đủ điểm."
    return earned_int, max_points, comment


def grade_submission(
    *,
    questions: list[dict[str, Any]],
    student_answers: Any,
    evidence_chunks: Any,
    scoring_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = scoring_policy or {}
    mcq_exact = bool(policy.get("mcq_exact", True))
    _ = bool(policy.get("essay_rubric", True))

    evidence_index = _build_evidence_index(evidence_chunks)

    breakdown: list[dict[str, Any]] = []
    total_points = 0
    earned_points = 0

    by_topic: dict[str, dict[str, float]] = {}
    by_difficulty: dict[str, dict[str, float]] = {}

    for q in questions or []:
        if not isinstance(q, dict):
            continue
        qid = q.get("question_id") or q.get("id")
        topic = str(q.get("topic") or "unknown")
        difficulty = str(q.get("difficulty") or "unknown")
        bloom = str(q.get("bloom_level") or "unknown")

        max_points = _to_int(q.get("max_points"), 1)
        ans = _extract_answer(student_answers, qid)

        comment = ""
        score_points = 0

        if "correct" in q:
            if mcq_exact:
                is_correct = _norm_text(ans) == _norm_text(q.get("correct"))
                score_points = max_points if is_correct else 0
                comment = "Đúng chính xác." if is_correct else "Sai đáp án MCQ (chấm exact match)."
            else:
                score_points = 0
                comment = "Chính sách hiện tại không hỗ trợ MCQ fuzzy."
        else:
            ev_text = _question_evidence_text(q, evidence_index)
            score_points, max_points, comment = _score_essay_with_rubric(q, ans, ev_text)

        total_points += max_points
        earned_points += score_points

        breakdown.append(
            {
                "question_id": qid,
                "topic": topic,
                "difficulty": difficulty,
                "bloom_level": bloom,
                "max_points": max_points,
                "score_points": score_points,
                "comment": comment,
            }
        )

        bt = by_topic.setdefault(topic, {"earned": 0.0, "total": 0.0, "percent": 0.0})
        bt["earned"] += score_points
        bt["total"] += max_points

        bd = by_difficulty.setdefault(difficulty, {"earned": 0.0, "total": 0.0, "percent": 0.0})
        bd["earned"] += score_points
        bd["total"] += max_points

    for group in (by_topic, by_difficulty):
        for row in group.values():
            total = float(row["total"])
            row["percent"] = round((float(row["earned"]) / total) * 100, 2) if total else 0.0
            row["earned"] = int(round(float(row["earned"])))
            row["total"] = int(round(total))

    strengths = []
    needs = []
    sorted_items = sorted(breakdown, key=lambda x: (x["score_points"] / max(1, x["max_points"])), reverse=True)
    for item in sorted_items[:3]:
        strengths.append(f"Câu {item['question_id']} ({item['topic']}): {item['score_points']}/{item['max_points']}.")
    for item in sorted_items[-3:]:
        needs.append(f"Câu {item['question_id']} ({item['topic']}): cần cải thiện vì {item['comment']}")

    next_steps = [
        "Đối chiếu lại từng câu sai với evidence_chunks trước khi nộp.",
        "Với tự luận, bám đúng rubric và dùng thuật ngữ xuất hiện trong tài liệu.",
        "Tự tạo 3-5 câu luyện tập theo topic có điểm thấp nhất rồi làm lại.",
    ]

    score_percent = int(round((earned_points / total_points) * 100)) if total_points else 0
    feedback_md = (
        "**3 điểm mạnh**\n"
        + "\n".join([f"- {s}" for s in strengths[:3]])
        + "\n\n**3 điểm cần cải thiện**\n"
        + "\n".join([f"- {n}" for n in needs[:3]])
        + "\n\n**3 việc nên làm tiếp theo**\n"
        + "\n".join([f"- {n}" for n in next_steps])
    )

    return {
        "score_percent": score_percent,
        "total_points": int(total_points),
        "earned_points": int(earned_points),
        "breakdown": breakdown,
        "by_topic": by_topic,
        "by_difficulty": by_difficulty,
        "student_feedback_md": feedback_md,
    }
