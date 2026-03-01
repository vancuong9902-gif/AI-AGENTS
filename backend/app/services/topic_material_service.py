from __future__ import annotations

from typing import Any

from app.services.llm_service import chat_json, llm_available


def _normalize_exercise(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    question = str(item.get("question") or "").strip()
    if not question:
        return None
    ex_type = str(item.get("type") or "exercise").strip().lower()[:40]
    options = item.get("options") if isinstance(item.get("options"), list) else None
    answer = str(item.get("answer") or "").strip()
    explanation = str(item.get("explanation") or "").strip()
    chunks = [int(x) for x in (item.get("source_chunks") or []) if str(x).isdigit()]
    out: dict[str, Any] = {
        "question": question[:1000],
        "type": ex_type or "exercise",
        "answer": answer[:800],
        "explanation": explanation[:2000],
        "source_chunks": chunks,
    }
    if options:
        out["options"] = [str(x).strip()[:300] for x in options if str(x).strip()][:8]
    return out


def _normalize_quiz_item(item: Any) -> dict[str, Any] | None:
    ex = _normalize_exercise(item)
    if not ex:
        return None
    if "options" not in ex or len(ex["options"]) < 2:
        return None
    return ex


def validate_material_payload(payload: dict[str, Any], included_chunk_ids: list[int]) -> tuple[bool, list[str], dict[str, Any]]:
    errs: list[str] = []
    allowed = set(int(x) for x in included_chunk_ids)

    theory = payload.get("theory") if isinstance(payload.get("theory"), dict) else {}
    theory_out = {
        "summary": str(theory.get("summary") or "").strip()[:1500],
        "key_concepts": [str(x).strip()[:220] for x in (theory.get("key_concepts") or []) if str(x).strip()][:20],
        "content_md": str(theory.get("content_md") or "").strip()[:12000],
    }

    ex_obj = payload.get("exercises") if isinstance(payload.get("exercises"), dict) else {}
    exercises_out: dict[str, list[dict[str, Any]]] = {"easy": [], "medium": [], "hard": []}

    for level in ("easy", "medium", "hard"):
        for raw in (ex_obj.get(level) or []):
            ex = _normalize_exercise(raw)
            if not ex:
                continue
            if not ex.get("source_chunks"):
                errs.append(f"exercise_{level}_missing_source_chunks")
                continue
            if any(int(cid) not in allowed for cid in ex["source_chunks"]):
                errs.append(f"exercise_{level}_invalid_source_chunks")
                continue
            exercises_out[level].append(ex)

    quiz_out: list[dict[str, Any]] = []
    for raw in (payload.get("mini_quiz") or []):
        q = _normalize_quiz_item(raw)
        if not q:
            continue
        if not q.get("source_chunks"):
            errs.append("quiz_missing_source_chunks")
            continue
        if any(int(cid) not in allowed for cid in q["source_chunks"]):
            errs.append("quiz_invalid_source_chunks")
            continue
        quiz_out.append(q)

    if len(quiz_out) != 5:
        errs.append("quiz_must_have_5_items")

    if not any(exercises_out.values()):
        errs.append("exercises_empty")

    normalized = {
        "theory": theory_out,
        "exercises": exercises_out,
        "mini_quiz": quiz_out[:5],
    }
    return (len(errs) == 0, errs, normalized)


def build_topic_material_with_llm(*, title: str, context_with_markers: str, included_chunk_ids: list[int]) -> tuple[dict[str, Any], list[str]]:
    theory_fallback = {
        "theory": {
            "summary": "",
            "key_concepts": [],
            "content_md": "",
        },
        "exercises": {"easy": [], "medium": [], "hard": []},
        "mini_quiz": [],
    }
    if not llm_available():
        return theory_fallback, ["llm_not_available"]

    prompt = f"""
Bạn là trợ giảng tạo tài liệu học theo đúng nguồn.
Chủ đề: {title}
Dữ liệu nguồn đã gắn marker [chunk:ID]. Mọi câu hỏi bài tập/quiz BẮT BUỘC có source_chunks lấy từ ID thật.
Chỉ dùng kiến thức trong ngữ cảnh. Không bịa.

Trả về STRICT JSON đúng schema:
{{
  "theory": {{"summary":"...", "key_concepts":["..."], "content_md":"..."}},
  "exercises": {{
    "easy":[{{"question":"...","type":"mcq|short|essay","options":["..."],"answer":"...","explanation":"...","source_chunks":[1,2]}}],
    "medium":[],
    "hard":[]
  }},
  "mini_quiz":[
    {{"question":"...","type":"mcq","options":["..."],"answer":"...","explanation":"...","source_chunks":[1]}}
  ]
}}

Yêu cầu:
- mini_quiz đúng 5 câu MCQ, mỗi câu >= 4 options.
- Mỗi item exercises/mini_quiz phải có source_chunks không rỗng.
- source_chunks chỉ được chọn từ các marker có trong ngữ cảnh.

Ngữ cảnh:
{context_with_markers[:50000]}
""".strip()

    warnings: list[str] = []
    normalized = None
    for attempt in range(2):
        raw = chat_json(messages=[{"role": "user", "content": prompt}], temperature=0.2, max_tokens=2500)
        ok, errs, parsed = validate_material_payload(raw if isinstance(raw, dict) else {}, included_chunk_ids)
        if ok:
            normalized = parsed
            break
        warnings.extend([f"attempt_{attempt + 1}:{e}" for e in errs])

    if normalized is None:
        warnings.append("material_validation_failed_theory_only")
        return theory_fallback, warnings

    return normalized, warnings
