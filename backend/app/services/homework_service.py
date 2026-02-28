from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.llm_service import chat_json, llm_available, pack_chunks
from app.services.heuristic_grader import grade_essay_heuristic


def _mode(val: Optional[str], *, default: str = "auto") -> str:
    m = (val or default).strip().lower()
    if m in {"0", "false", "no"}:
        return "off"
    return m


def _cap_int(v: Any, *, default: int, lo: int, hi: int) -> int:
    try:
        i = int(v)
    except Exception:
        i = int(default)
    return max(lo, min(hi, i))


def _compact(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _sanitize_rubric(rubric: Any, *, max_points: int) -> List[Dict[str, Any]]:
    mp = _cap_int(max_points, default=10, lo=1, hi=100)

    items: List[Dict[str, Any]] = []
    if isinstance(rubric, dict):
        rubric = [rubric]
    if isinstance(rubric, list):
        for it in rubric:
            if not isinstance(it, dict):
                continue
            crit = _compact(str(it.get("criterion") or ""))
            if not crit:
                continue
            try:
                pts = int(it.get("points", 0) or 0)
            except Exception:
                pts = 0
            if pts <= 0:
                continue
            items.append({"criterion": crit, "points": pts})

    if not items:
        # basic fallback
        p1 = max(1, mp // 3)
        p2 = max(1, mp // 3)
        p3 = max(1, mp - p1 - p2)
        items = [
            {"criterion": "Đúng trọng tâm và chính xác về chủ đề", "points": p1},
            {"criterion": "Giải thích rõ ràng, có ví dụ/lập luận", "points": p2},
            {"criterion": "Trình bày mạch lạc, thuật ngữ đúng", "points": p3},
        ]

    # normalize sum
    s = sum(int(x.get("points", 0) or 0) for x in items)
    if s <= 0:
        items[0]["points"] = mp
    elif s != mp:
        drift = mp - s
        items[0]["points"] = max(1, int(items[0]["points"]) + drift)

    # final safety
    s2 = sum(int(x.get("points", 0) or 0) for x in items)
    if s2 != mp:
        items = [{"criterion": "Đúng trọng tâm và có giải thích", "points": mp}]

    return items


def _fetch_chunks(db: Session, sources: Any) -> List[Dict[str, Any]]:
    if isinstance(sources, dict):
        sources = [sources]
    ids: List[int] = []
    if isinstance(sources, list):
        for it in sources:
            cid = it.get("chunk_id") if isinstance(it, dict) else it
            try:
                ids.append(int(cid))
            except Exception:
                continue
    ids = list(dict.fromkeys(ids))[:10]
    if not ids:
        return []

    rows = db.query(DocumentChunk).filter(DocumentChunk.id.in_(ids)).all()
    dids = list({int(r.document_id) for r in rows if getattr(r, "document_id", None) is not None})
    dmap: Dict[int, str] = {}
    if dids:
        docs = db.query(Document).filter(Document.id.in_(dids)).all()
        dmap = {int(d.id): (d.title or str(d.id)) for d in docs}

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "chunk_id": int(r.id),
                "document_id": int(r.document_id) if getattr(r, "document_id", None) is not None else None,
                "document_title": dmap.get(int(r.document_id)) if getattr(r, "document_id", None) is not None else None,
                "text": r.text,
            }
        )
    return out


def grade_homework(
    db: Session,
    *,
    user_id: int | None = None,
    stem: str,
    answer_text: str,
    max_points: int,
    rubric: Any,
    sources: Any,
) -> Dict[str, Any]:
    # user_id is kept for API compatibility / future persistence
    _ = user_id
    mode = _mode(getattr(settings, "HOMEWORK_AUTO_GRADE", "auto"))
    if mode == "off":
        raise HTTPException(status_code=400, detail="HOMEWORK_AUTO_GRADE=off")

    use_llm = bool(llm_available())
    # auto: only grade when LLM is available; always: grade even offline (heuristic)
    if (mode == "auto") and (not use_llm):
        raise HTTPException(
            status_code=400,
            detail="LLM chưa được cấu hình nên không thể chấm tự luận (HOMEWORK_AUTO_GRADE=auto). Hãy set OPENAI_API_KEY hoặc OPENAI_BASE_URL trong backend/.env, hoặc đặt HOMEWORK_AUTO_GRADE=always để chấm offline (heuristic).",
        )

    mp = _cap_int(max_points, default=int(getattr(settings, "HOMEWORK_MAX_POINTS", 10) or 10), lo=1, hi=100)
    stem2 = _compact(stem)
    if len(stem2) < 10:
        raise HTTPException(status_code=422, detail="Stem quá ngắn")

    min_chars = _cap_int(getattr(settings, "HOMEWORK_MIN_CHARS", 40), default=40, lo=0, hi=2000)
    ans = (answer_text or "").strip()
    if len(ans) < min_chars:
        return {
            "score_points": 0,
            "max_points": mp,
            "comment": f"Câu trả lời quá ngắn (<{min_chars} ký tự). Hãy viết rõ ý theo rubric.",
            "rubric_breakdown": [],
        }

    rb = _sanitize_rubric(rubric, max_points=mp)
    evidence = _fetch_chunks(db, sources)
    packed = pack_chunks(evidence, max_chunks=8)

    # Offline heuristic grading (no LLM)
    if not use_llm:
        data = grade_essay_heuristic(
            stem=stem2,
            answer_text=ans,
            rubric=rb,
            max_points=int(mp),
            evidence_chunks=evidence,
        )
        # ensure expected shape
        return {
            "score_points": int(data.get("score_points", 0) or 0),
            "max_points": int(mp),
            "comment": data.get("comment") or "Bài làm đã được chấm (heuristic).",
            "rubric_breakdown": data.get("rubric_breakdown") or [],
        }

    system = """Bạn là GIẢNG VIÊN CHẤM BÀI TẬP VỀ NHÀ (TỰ LUẬN).
Chỉ dựa trên: (1) câu hỏi, (2) bài làm học sinh, (3) rubric, (4) evidence_chunks.
KHÔNG dùng kiến thức ngoài evidence_chunks.

Yêu cầu:
- Chấm điểm chặt, công bằng, đúng rubric.
- Nếu bài trả lời sai trọng tâm hoặc bịa ngoài evidence => trừ điểm mạnh.
- Trả về JSON hợp lệ, không thêm chữ ngoài JSON.

ĐẦU RA:
{
  "score_points": <int 0..max_points>,
  "comment": "feedback ngắn 2-5 câu, sư phạm",
  "rubric_breakdown": [
    {"criterion":"...","max_points":<int>,"points_awarded":<int>,"comment":"..."}
  ]
}
"""

    user = {
        "question": {"stem": stem2, "max_points": int(mp), "rubric": rb},
        "answer_text": ans,
        "evidence_chunks": packed,
    }

    data = chat_json(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=1200,
    )

    if not isinstance(data, dict):
        return {
            "score_points": 0,
            "max_points": mp,
            "comment": "Không chấm được (đầu ra không hợp lệ).",
            "rubric_breakdown": [],
        }

    try:
        sp = int(data.get("score_points", 0) or 0)
    except Exception:
        sp = 0
    sp = max(0, min(mp, sp))

    rbd = data.get("rubric_breakdown")
    if isinstance(rbd, dict):
        rbd = [rbd]

    out_rb: List[Dict[str, Any]] = []
    if isinstance(rbd, list):
        for it in rbd:
            if not isinstance(it, dict):
                continue
            crit = _compact(str(it.get("criterion") or ""))
            if not crit:
                continue
            try:
                mx = int(it.get("max_points", 0) or 0)
            except Exception:
                mx = 0
            try:
                pa = int(it.get("points_awarded", 0) or 0)
            except Exception:
                pa = 0
            if mx <= 0:
                # infer from rubric
                mx = next((int(x.get("points", 0) or 0) for x in rb if _compact(str(x.get("criterion") or "")) == crit), 0)
            if mx <= 0:
                continue
            pa = max(0, min(mx, pa))
            out_rb.append(
                {
                    "criterion": crit,
                    "max_points": int(mx),
                    "points_awarded": int(pa),
                    "comment": _compact(str(it.get("comment") or "")) or None,
                }
            )

    if out_rb:
        total_pa = sum(int(x.get("points_awarded", 0) or 0) for x in out_rb)
        if total_pa != sp:
            drift = sp - total_pa
            out_rb[0]["points_awarded"] = max(0, min(int(out_rb[0]["max_points"]), int(out_rb[0]["points_awarded"]) + drift))

    comment = _compact(str(data.get("comment") or ""))
    if not comment:
        comment = "Bài làm đã được chấm theo rubric."

    return {"score_points": sp, "max_points": mp, "comment": comment, "rubric_breakdown": out_rb}


def _normalize_original_exercises(original: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(original, list):
        return out
    for item in original:
        if not isinstance(item, dict):
            continue
        question = _compact(str(item.get("question") or ""))
        if not question:
            continue
        q_type = _compact(str(item.get("type") or "exercise")).lower() or "exercise"
        if q_type not in {"mcq", "essay", "exercise"}:
            q_type = "exercise"
        options = item.get("options")
        if not isinstance(options, list):
            options = None
        answer = item.get("answer")
        answer = _compact(str(answer)) if answer is not None and _compact(str(answer)) else None
        out.append(
            {
                "type": q_type,
                "question": question,
                "options": options,
                "answer": answer,
                "source": "original_pdf",
            }
        )
    return out


def _generate_ai_exercises(topic: Any, n_questions: int = 5) -> List[Dict[str, Any]]:
    title = _compact(str(getattr(topic, "title", "") or ""))
    summary = _compact(str(getattr(topic, "summary", "") or ""))
    if llm_available() and title:
        prompt = (
            "Tạo bộ bài tập học tập bằng tiếng Việt dưới dạng JSON array. "
            "Mỗi phần tử gồm type (mcq/essay/exercise), question, options (array hoặc null), answer (string hoặc null), source='ai_generated'. "
            f"Chủ đề: {title}. Tóm tắt: {summary}. Số lượng: {int(n_questions)}."
        )
        try:
            data = chat_json(messages=[{"role": "user", "content": prompt}], max_tokens=1200)
            if isinstance(data, list):
                out: List[Dict[str, Any]] = []
                for x in data[: max(1, int(n_questions))]:
                    if not isinstance(x, dict):
                        continue
                    q = _compact(str(x.get("question") or ""))
                    if not q:
                        continue
                    out.append(
                        {
                            "type": _compact(str(x.get("type") or "exercise")).lower() or "exercise",
                            "question": q,
                            "options": x.get("options") if isinstance(x.get("options"), list) else None,
                            "answer": _compact(str(x.get("answer") or "")) or None,
                            "source": "ai_generated",
                        }
                    )
                if out:
                    return out[: max(1, int(n_questions))]
        except Exception:
            pass

    # deterministic fallback
    count = max(1, int(n_questions))
    base = title or "chủ đề"
    return [
        {
            "type": "exercise",
            "question": f"Trình bày ngắn gọn kiến thức trọng tâm của {base} (câu {i+1}).",
            "options": None,
            "answer": None,
            "source": "ai_generated",
        }
        for i in range(count)
    ]


def _mix_original_and_ai(original: List[Dict[str, Any]], topic: Any, n_questions: int = 5) -> List[Dict[str, Any]]:
    count = max(1, int(n_questions))
    original_norm = _normalize_original_exercises(original)
    if len(original_norm) >= count:
        return original_norm[:count]
    missing = count - len(original_norm)
    ai = _generate_ai_exercises(topic, missing)
    return (original_norm + ai)[:count]


def generate_homework(topic: Any, n_questions: int = 5) -> List[Dict[str, Any]]:
    metadata = getattr(topic, "metadata_json", None) or {}
    original = metadata.get("original_exercises", []) if isinstance(metadata, dict) else []
    if original:
        return _mix_original_and_ai(original, topic, n_questions)
    return _generate_ai_exercises(topic, n_questions)
