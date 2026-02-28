from __future__ import annotations

import json
import re
from math import ceil
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_topic import DocumentTopic
from app.schemas.profile import (
    HomeworkPrompt,
    HomeworkMCQQuestion,
    LearningModule,
    LearningPlanDay,
    LearningPlanTask,
    TeacherLearningPlan,
)
from app.services.llm_service import chat_json, llm_available, pack_chunks


ADAPTIVE_LEVEL_CONFIG: Dict[str, Dict[str, Any]] = {
    "gioi": {
        "label": "Giỏi",
        "difficulty_mix": {"hard": 0.6, "medium": 0.3, "easy": 0.1},
        "material_style": "Ưu tiên section nâng cao + external references",
        "reason_prefix": "Tăng cường tư duy bậc cao (Bloom: evaluate/create)",
    },
    "kha": {
        "label": "Khá",
        "difficulty_mix": {"hard": 0.3, "medium": 0.5, "easy": 0.2},
        "material_style": "Cân bằng kiến thức mới và phần ôn tập theo chủ đề yếu",
        "reason_prefix": "Cân bằng học mới + củng cố weak topics",
    },
    "trung_binh": {
        "label": "Trung bình",
        "difficulty_mix": {"hard": 0.1, "medium": 0.4, "easy": 0.5},
        "material_style": "Bắt đầu từ nền tảng, nhiều ví dụ minh hoạ",
        "reason_prefix": "Ưu tiên kiến thức cốt lõi và ví dụ thực hành",
    },
    "yeu": {
        "label": "Yếu",
        "difficulty_mix": {"hard": 0.0, "medium": 0.2, "easy": 0.8},
        "material_style": "Video/text explanation ưu tiên, học lại nền tảng",
        "reason_prefix": "Cần củng cố nền tảng trước khi tăng độ khó",
    },
}


def _level_from_score(score: int | float | None) -> str:
    s = float(score or 0)
    if s >= 85:
        return "gioi"
    if s >= 70:
        return "kha"
    if s >= 50:
        return "trung_binh"
    return "yeu"


def _pick_difficulty_sequence(total: int, mix: Dict[str, float]) -> List[str]:
    n = max(0, int(total or 0))
    if n <= 0:
        return []

    raw = {k: max(0.0, float(v or 0.0)) for k, v in (mix or {}).items()}
    if sum(raw.values()) <= 0:
        raw = {"hard": 0.2, "medium": 0.5, "easy": 0.3}

    counts = {k: int(n * v) for k, v in raw.items()}
    remain = n - sum(counts.values())
    priority = sorted(raw.items(), key=lambda x: x[1], reverse=True)
    i = 0
    while remain > 0 and priority:
        counts[priority[i % len(priority)][0]] = counts.get(priority[i % len(priority)][0], 0) + 1
        remain -= 1
        i += 1

    seq: List[str] = []
    for k in ["easy", "medium", "hard"]:
        seq.extend([k] * int(counts.get(k, 0)))
    return seq[:n]


def generate_learning_plan_items(
    *,
    user_id: int,
    classroom_id: int,
    level: str,
    weak_topics: List[Dict[str, Any]] | List[str],
    all_topics: List[Dict[str, Any]] | List[str],
) -> Dict[str, Any]:
    """Sinh danh sách item adaptive theo level, weak topics và toàn bộ topics."""

    lvl = (level or "").strip().lower() or "trung_binh"
    if lvl not in ADAPTIVE_LEVEL_CONFIG:
        lvl = "trung_binh"
    cfg = ADAPTIVE_LEVEL_CONFIG[lvl]

    def _normalize_topic(tp: Any, fallback_id: int) -> Dict[str, Any]:
        if isinstance(tp, dict):
            title = str(tp.get("title") or tp.get("topic") or f"Topic {fallback_id}").strip()
            tid = int(tp.get("id") or tp.get("topic_id") or fallback_id)
        else:
            title = str(tp or f"Topic {fallback_id}").strip()
            tid = int(fallback_id)
        return {"id": tid, "title": title}

    weak_norm = [_normalize_topic(t, idx + 1) for idx, t in enumerate(weak_topics or [])]
    all_norm = [_normalize_topic(t, idx + 100) for idx, t in enumerate(all_topics or [])]

    prioritized = weak_norm + [t for t in all_norm if t["title"] not in {w["title"] for w in weak_norm}]
    prioritized = [t for t in prioritized if t.get("title")]
    if not prioritized:
        prioritized = [{"id": 1, "title": "Tổng quan kiến thức"}]

    order = 1
    items: List[Dict[str, Any]] = []
    homework_difficulties = _pick_difficulty_sequence(len(prioritized), cfg["difficulty_mix"])

    for idx, topic in enumerate(prioritized):
        topic_id = int(topic["id"])
        topic_title = str(topic["title"])
        is_weak = topic_title in {w["title"] for w in weak_norm}

        items.append(
            {
                "type": "study_material",
                "topic_id": topic_id,
                "topic_title": topic_title,
                "content_ref": f"doc_section:{topic_id}:advanced" if lvl == "gioi" else f"doc_section:{topic_id}:core",
                "difficulty": "hard" if lvl == "gioi" else ("easy" if lvl == "yeu" else "medium"),
                "estimated_minutes": 20 if lvl in {"gioi", "kha"} else 25,
                "order": order,
                "reason": (
                    f"{cfg['reason_prefix']}. Tài liệu: {cfg['material_style']}."
                    + (" Chủ đề này đang yếu nên cần ưu tiên ôn lại." if is_weak else "")
                ),
            }
        )
        order += 1

        if lvl == "gioi":
            items.append(
                {
                    "type": "homework",
                    "topic_id": topic_id,
                    "topic_title": topic_title,
                    "content_ref": f"challenge_problem:{topic_id}",
                    "difficulty": "hard",
                    "estimated_minutes": 25,
                    "order": order,
                    "reason": "Challenge problems giúp mở rộng tư duy phản biện và bài toán mở.",
                }
            )
        else:
            diff = homework_difficulties[idx] if idx < len(homework_difficulties) else "medium"
            items.append(
                {
                    "type": "homework",
                    "topic_id": topic_id,
                    "topic_title": topic_title,
                    "content_ref": f"practice_set:{topic_id}:{diff}",
                    "difficulty": diff,
                    "estimated_minutes": 20,
                    "order": order,
                    "reason": f"Phân phối độ khó theo level {cfg['label']} để tối ưu tiến độ học.",
                }
            )

        order += 1
        items.append(
            {
                "type": "quiz",
                "topic_id": topic_id,
                "topic_title": topic_title,
                "content_ref": f"quiz:{topic_id}:adaptive",
                "difficulty": "medium" if lvl != "gioi" else "hard",
                "estimated_minutes": 10,
                "order": order,
                "reason": "Mini quiz giúp đo mức hiểu bài ngay sau khi học.",
            }
        )
        order += 1

    if lvl == "yeu":
        items.append(
            {
                "type": "study_material",
                "topic_id": int(prioritized[0]["id"]),
                "topic_title": "Tutor AI session",
                "content_ref": "tutor_ai:foundation_boost",
                "difficulty": "easy",
                "estimated_minutes": 15,
                "order": order,
                "reason": "Khuyến nghị mạnh Tutor AI sessions để kèm nền tảng theo từng bước.",
            }
        )

    return {
        "user_id": int(user_id),
        "classroom_id": int(classroom_id or 0),
        "student_level": lvl,
        "items": items,
        "total_items": len(items),
    }


def create_learning_plan(
    *,
    user_id: int,
    classroom_id: int,
    diagnostic_result: Dict[str, Any] | None,
    all_topics: List[Dict[str, Any]] | List[str],
) -> Dict[str, Any]:
    """Tạo learning plan adaptive theo điểm đầu vào và chủ đề yếu."""

    dr = diagnostic_result or {}
    score = float(dr.get("score") or dr.get("overall_score") or 0)
    level = _level_from_score(score)
    weak_topics = dr.get("weak_topics") or []

    plan = generate_learning_plan_items(
        user_id=int(user_id),
        classroom_id=int(classroom_id or 0),
        level=level,
        weak_topics=weak_topics,
        all_topics=all_topics,
    )

    est_days = max(1, ceil((sum(int(i.get("estimated_minutes") or 15) for i in plan["items"]) / 45)))
    plan["estimated_completion_days"] = int(est_days)
    plan["diagnostic_score"] = score
    return plan


def build_personalized_content_plan(
    db: Session,
    user_id: int,
    quiz_attempt_result: Dict[str, Any],
    document_topics: List[str] | List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Proxy personalized planning to LMS service for reuse in learning-plan flows."""

    from app.services.lms_service import build_personalized_content_plan as _build_plan

    return _build_plan(
        db=db,
        user_id=int(user_id),
        quiz_attempt_result=quiz_attempt_result or {},
        document_topics=document_topics or [],
    )


def create_learning_plan(
    db: Session,
    *,
    user_id: int,
    classroom_id: int | None,
    level: str,
    weak_topics: List[str] | None = None,
    teacher_id: int | None = None,
) -> Dict[str, Any]:
    """Create a lightweight learning plan payload from diagnostic results."""

    from app.services.learning_plan_storage_service import save_teacher_plan

    assigned_topic = next((str(t).strip() for t in (weak_topics or []) if str(t).strip()), None)
    days_total = int(getattr(settings, "LEARNING_PLAN_DAYS", 7) or 7)
    minutes_per_day = int(getattr(settings, "LEARNING_PLAN_MINUTES_PER_DAY", 35) or 35)

    teacher_plan = build_teacher_learning_plan(
        db,
        user_id=int(user_id),
        teacher_id=int(teacher_id or settings.DEFAULT_TEACHER_ID or 1),
        level=str(level or "beginner"),
        assigned_topic=assigned_topic,
        modules=[],
        days=days_total,
        minutes_per_day=minutes_per_day,
    )
    payload = teacher_plan.model_dump()
    payload["weak_topics"] = [str(t) for t in (weak_topics or []) if str(t).strip()]

    row = save_teacher_plan(
        db,
        user_id=int(user_id),
        teacher_id=int(teacher_id or settings.DEFAULT_TEACHER_ID or 1),
        classroom_id=int(classroom_id) if classroom_id is not None else None,
        assigned_topic=assigned_topic,
        level=str(level or "beginner"),
        days_total=int(teacher_plan.days_total or days_total),
        minutes_per_day=int(teacher_plan.minutes_per_day or minutes_per_day),
        teacher_plan=payload,
    )

    return {"plan_id": int(row.id), "assigned_topic": assigned_topic}


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


def _fetch_chunks(db: Session, chunk_ids: List[int]) -> List[Dict[str, Any]]:
    ids = [int(x) for x in (chunk_ids or []) if isinstance(x, (int, str)) and str(x).strip().isdigit()]
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


def _title_tokens(title: str, *, max_tokens: int = 4) -> List[str]:
    t = (title or '').lower()
    toks = [x for x in re.findall(r"[\wÀ-ỹ]{3,}", t) if x]
    return list(dict.fromkeys(toks))[:max_tokens]


def _chunk_ids_for_document_topic(db: Session, dt: DocumentTopic, *, limit: int = 10) -> List[int]:
    """Find representative chunk ids for a DocumentTopic.

    Priority:
    1) Use start/end chunk_index range when available.
    2) Keyword/title token search within the same document.
    3) Fallback to first chunks of that document.
    """

    lim = max(3, min(20, int(limit or 10)))

    # 1) range mapping
    s = getattr(dt, 'start_chunk_index', None)
    e = getattr(dt, 'end_chunk_index', None)
    if s is not None and e is not None:
        try:
            s_i, e_i = int(s), int(e)
            if s_i > e_i:
                s_i, e_i = e_i, s_i
            rows = (
                db.query(DocumentChunk.id)
                .filter(DocumentChunk.document_id == int(dt.document_id))
                .filter(DocumentChunk.chunk_index >= int(s_i))
                .filter(DocumentChunk.chunk_index <= int(e_i))
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(lim)
                .all()
            )
            ids = [int(r[0]) for r in rows if r and r[0] is not None]
            if ids:
                return ids
        except Exception:
            pass

    # 2) keyword / title token search
    keys: List[str] = []
    try:
        keys.extend([str(x) for x in (dt.keywords or [])])
    except Exception:
        keys = []
    keys = [k.strip() for k in keys if isinstance(k, str) and len(k.strip()) >= 3]
    keys = list(dict.fromkeys(keys))[:3]
    keys.extend(_title_tokens(getattr(dt, 'title', ''), max_tokens=2))

    conds = []
    for k in keys:
        if not k:
            continue
        conds.append(DocumentChunk.text.ilike(f"%{k}%"))

    if conds:
        try:
            rows = (
                db.query(DocumentChunk.id)
                .filter(DocumentChunk.document_id == int(dt.document_id))
                .filter(or_(*conds))
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(lim)
                .all()
            )
            ids = [int(r[0]) for r in rows if r and r[0] is not None]
            if ids:
                return ids
        except Exception:
            pass

    # 3) fallback: first chunks of doc
    try:
        rows = (
            db.query(DocumentChunk.id)
            .filter(DocumentChunk.document_id == int(dt.document_id))
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(min(lim, 6))
            .all()
        )
        return [int(r[0]) for r in rows if r and r[0] is not None]
    except Exception:
        return []


def _fetch_teacher_topic_units(
    db: Session,
    *,
    assigned_topic: Optional[str],
    modules: List[LearningModule],
    preferred_user_id: Optional[int] = None,
    max_docs: int = 2,
) -> List[Dict[str, Any]]:
    """Fetch teacher-authored topic outline (DocumentTopic) ordered by topic_index.

    We try to pick document_ids that best match `assigned_topic` (or first module topic).
    If nothing matches, we fall back to the most recent document that has document_topics.
    """

    q = (assigned_topic or '').strip()
    if not q:
        # fallback to first module topic
        for m in (modules or []):
            if isinstance(m, LearningModule) and (m.topic or '').strip():
                q = m.topic.strip()
                break

    doc_ids: List[int] = []
    try:
        from app.services.rag_service import auto_document_ids_for_query

        if q:
            doc_ids = auto_document_ids_for_query(
                db,
                q,
                preferred_user_id=int(preferred_user_id) if preferred_user_id is not None else getattr(settings, 'DEFAULT_TEACHER_ID', 1),
                max_docs=max(1, min(3, int(max_docs or 2))),
            )
    except Exception:
        doc_ids = []

    if not doc_ids:
        try:
            # pick most recent doc that has topics
            row = db.query(DocumentTopic.document_id).order_by(DocumentTopic.created_at.desc()).limit(1).first()
            if row and row[0] is not None:
                doc_ids = [int(row[0])]
        except Exception:
            doc_ids = []

    units: List[Dict[str, Any]] = []
    for did in (doc_ids or [])[: max(1, min(3, int(max_docs or 2)))]:
        try:
            rows = (
                db.query(DocumentTopic)
                .filter(DocumentTopic.document_id == int(did))
                .order_by(DocumentTopic.topic_index.asc())
                .all()
            )
        except Exception:
            rows = []

        for dt in rows or []:
            title = _compact(getattr(dt, 'title', '') or '')
            if not title:
                continue
            chunk_ids = _chunk_ids_for_document_topic(db, dt, limit=10)
            units.append(
                {
                    'title': title,
                    'document_id': int(getattr(dt, 'document_id', did) or did),
                    'topic_index': int(getattr(dt, 'topic_index', 0) or 0),
                    'summary': _compact(getattr(dt, 'summary', '') or ''),
                    'keywords': list(getattr(dt, 'keywords', []) or [])[:6],
                    'chunk_ids': chunk_ids,
                    'original_exercises': ((getattr(dt, 'metadata_json', {}) or {}).get('original_exercises') if isinstance(getattr(dt, 'metadata_json', {}), dict) else []),
                }
            )

    return units


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

    # fallback rubric if missing
    if not items:
        # split points into 3 buckets
        p1 = max(1, mp // 3)
        p2 = max(1, mp // 3)
        p3 = max(1, mp - p1 - p2)
        items = [
            {"criterion": "Đúng trọng tâm và chính xác về chủ đề", "points": p1},
            {"criterion": "Giải thích/diễn giải rõ ràng, có ví dụ hoặc lập luận", "points": p2},
            {"criterion": "Nêu được lưu ý/lỗi thường gặp hoặc điều kiện áp dụng", "points": p3},
        ]

    # normalize total to max_points
    total = sum(int(x.get("points", 0) or 0) for x in items)
    if total != mp and items:
        # scale then fix drift
        if total > 0:
            scaled = []
            for x in items:
                scaled.append({"criterion": x["criterion"], "points": max(1, round(int(x["points"]) * mp / total))})
            items = scaled
        drift = mp - sum(int(x["points"]) for x in items)
        items[0]["points"] = max(1, int(items[0]["points"]) + drift)

    # keep at most 4 criteria
    items = items[:4]
    # final clamp
    for x in items:
        x["points"] = _cap_int(x.get("points"), default=1, lo=1, hi=mp)
    # re-fix drift
    drift = mp - sum(int(x["points"]) for x in items)
    if items and drift:
        items[0]["points"] = max(1, min(mp, int(items[0]["points"]) + drift))

    return items


def _offline_homework(topic: str, *, level: str, max_points: int, sources: List[int]) -> HomeworkPrompt:
    t = (topic or "tài liệu").strip()
    mp = _cap_int(max_points, default=int(getattr(settings, "HOMEWORK_MAX_POINTS", 10) or 10), lo=5, hi=30)

    if level == "beginner":
        stem = (
            f"Chủ đề '{t}': Hãy giải thích ngắn gọn khái niệm/chủ điểm chính của '{t}'. "
            "Sau đó nêu 1 ví dụ minh hoạ và 1 lỗi thường gặp (hoặc điều kiện áp dụng) nếu có."
        )
    elif level == "advanced":
        stem = (
            f"Chủ đề '{t}': Hãy phân tích một tình huống/ví dụ thực tiễn liên quan '{t}' và đề xuất cách xử lý/giải pháp phù hợp. "
            "Nêu rõ lý do, bước làm/tiêu chí, và cảnh báo sai lầm thường gặp."
        )
    else:
        stem = (
            f"Chủ đề '{t}': Hãy trình bày lại nội dung trọng tâm của '{t}' (2–4 ý). "
            "Sau đó so sánh 2 trường hợp/khái niệm liên quan (nếu có) và nêu 1 ví dụ minh hoạ."
        )

    rubric = _sanitize_rubric(None, max_points=mp)
    src = [{"chunk_id": int(sources[0])}] if sources else []
    return HomeworkPrompt(stem=stem, max_points=mp, rubric=rubric, sources=src)


def _llm_homework(topic: str, *, level: str, max_points: int, evidence_chunks: List[Dict[str, Any]]) -> Optional[HomeworkPrompt]:
    if not evidence_chunks:
        return None

    gen_mode = _mode(getattr(settings, "HOMEWORK_LLM_GEN", "auto"), default="auto")
    if gen_mode in {"off", "offline"}:
        return None
    if gen_mode in {"auto", "llm"} and not llm_available():
        return None

    packed = pack_chunks(evidence_chunks, max_chunks=8, max_chars_per_chunk=850, max_total_chars=4200)
    if not packed:
        return None
    valid_ids = [int(c["chunk_id"]) for c in packed if isinstance(c, dict) and c.get("chunk_id") is not None]

    mp = _cap_int(max_points, default=int(getattr(settings, "HOMEWORK_MAX_POINTS", 10) or 10), lo=5, hi=30)
    topic_clean = (topic or "tài liệu").strip() or "tài liệu"

    system = """Bạn là GIÁO VIÊN giao BÀI TẬP VỀ NHÀ.
Chỉ dựa trên evidence_chunks (không dùng kiến thức ngoài).
Không chép nguyên văn; diễn đạt sư phạm, rõ ràng.

Yêu cầu đầu ra JSON hợp lệ, KHÔNG thêm chữ ngoài JSON.

ĐẦU RA:
{
  "stem": "..." ,
  "max_points": <int>,
  "rubric": [{"criterion":"...","points":<int>}],
  "sources": [{"chunk_id": <int>}]
}

Ràng buộc:
- stem phải bắt đầu bằng: Chủ đề '<TOPIC>': ...
- stem 2–4 câu, ưu tiên vận dụng/giải thích/so sánh/tình huống (tuỳ level).
- rubric 3–4 tiêu chí, tổng points = max_points.
- sources chỉ lấy chunk_id từ evidence_chunks.
"""

    user = {
        "topic": topic_clean,
        "level": level,
        "max_points": mp,
        "evidence_chunks": packed,
    }

    try:
        data = chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.35,
            max_tokens=900,
        )
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    stem = _compact(str(data.get("stem") or ""))
    if len(stem) < 30:
        return None

    # enforce prefix
    if not re.search(r"^Chủ\s*đề\s*'", stem, flags=re.I):
        stem = f"Chủ đề '{topic_clean}': {stem}"

    try:
        mp2 = int(data.get("max_points", mp) or mp)
    except Exception:
        mp2 = mp
    mp2 = _cap_int(mp2, default=mp, lo=5, hi=30)

    rubric = _sanitize_rubric(data.get("rubric"), max_points=mp2)

    srcs = data.get("sources")
    if isinstance(srcs, dict):
        srcs = [srcs]
    out_src: List[Dict[str, int]] = []
    if isinstance(srcs, list):
        for it in srcs:
            cid = it.get("chunk_id") if isinstance(it, dict) else it
            try:
                cid_i = int(cid)
            except Exception:
                continue
            if cid_i in valid_ids:
                out_src.append({"chunk_id": cid_i})
    out_src = out_src[:2]
    if not out_src and valid_ids:
        out_src = [{"chunk_id": int(valid_ids[0])}]

    return HomeworkPrompt(stem=stem, max_points=mp2, rubric=rubric, sources=out_src)


def _offline_day_lesson(
    day_title: str,
    *,
    level: str,
    objectives: List[str],
    outline: List[Dict[str, Any]],
    evidence_chunks: List[Dict[str, Any]],
) -> str:
    """Offline "textbook-like" daily lesson.

    This is intentionally simple but readable: objectives, key points, quick example, self-check.
    """

    lvl = (level or "beginner").strip().lower()
    title = (day_title or "Bài học").strip() or "Bài học"

    obj_md = "\n".join([f"- {o}" for o in (objectives or []) if str(o).strip()])
    if not obj_md:
        obj_md = "- Nắm được ý chính của bài học và làm được bài tập về nhà."

    points: List[str] = []
    for it in (outline or [])[:4]:
        if not isinstance(it, dict):
            continue
        t = _compact(str(it.get("title") or ""))
        s = _compact(str(it.get("summary") or ""))
        if t and s:
            points.append(f"- **{t}**: {s}")

    # If summaries are missing, extract a few "useful" sentences from evidence.
    if len(points) < 2:
        text = " ".join([str(c.get("text") or "").strip() for c in (evidence_chunks or []) if isinstance(c, dict)])
        text = " ".join(text.split())
        if text:
            raw = text.replace("\n", ". ")
            parts = [p.strip() for p in re.split(r"[\.\!\?]", raw) if p.strip()]
            for p in parts:
                if len(p) < 35:
                    continue
                points.append(f"- {p}.")
                if len(points) >= 6:
                    break

    if not points:
        points = ["- Đọc kỹ phần định nghĩa/khái niệm và ghi chú lại ý chính.", "- Làm ví dụ nhỏ để kiểm tra hiểu bài."]

    focus = {
        "beginner": "Tập trung vào khái niệm + ví dụ đơn giản.",
        "intermediate": "Tập trung vào so sánh/đối chiếu + lỗi thường gặp.",
        "advanced": "Tập trung vào vận dụng tình huống + lý do/tiêu chí lựa chọn.",
    }.get(lvl, "Tập trung vào khái niệm + ví dụ.")

    return (
        f"# {title}\n"
        f"\n"
        f"**Mức độ gợi ý:** {lvl}\n\n"
        f"## Mục tiêu\n{obj_md}\n\n"
        f"## Trọng tâm cần nắm\n{focus}\n\n"
        f"## Nội dung chính\n" + "\n".join(points) + "\n\n"
        f"## Ví dụ nhanh\n"
        f"- Hãy tự tạo 1 ví dụ nhỏ minh hoạ cho bài hôm nay (2–6 dòng).\n"
        f"- Nếu gặp lỗi/sai, hãy ghi lại: *Vì sao sai?* và *sửa thế nào?*\n\n"
        f"## Tự kiểm tra\n"
        f"1) Nêu 2 ý quan trọng nhất của bài hôm nay.\n"
        f"2) Viết 1 ví dụ ngắn áp dụng đúng.\n"
        f"3) Nêu 1 lỗi thường gặp và cách tránh.\n"
    )


def _llm_day_lesson(
    *,
    day_title: str,
    level: str,
    objectives: List[str],
    outline: List[Dict[str, Any]],
    evidence_chunks: List[Dict[str, Any]],
) -> Optional[str]:
    """LLM-based daily lesson generator (textbook style)."""

    gen_mode = _mode(getattr(settings, "LESSON_GEN_MODE", "auto"), default="auto")
    if gen_mode in {"off", "offline"}:
        return None
    if gen_mode in {"auto", "llm"} and not llm_available():
        return None
    if not evidence_chunks:
        return None

    packed = pack_chunks(evidence_chunks, max_chunks=6, max_chars_per_chunk=900, max_total_chars=5200)
    if not packed:
        return None

    system = """Bạn là GIÁO VIÊN.
Hãy viết 1 BÀI HỌC kiểu "sách giáo khoa" cho học sinh: rõ ràng, có cấu trúc, dễ học.
Chỉ dựa trên evidence_chunks (KHÔNG dùng kiến thức ngoài).
Không chép nguyên văn; diễn đạt lại sư phạm.

YÊU CẦU:
- Dùng Markdown.
- Có các phần tối thiểu: Mục tiêu, Nội dung chính, Ví dụ, Lỗi thường gặp, Tự kiểm tra.
- Nếu evidence không đủ để trả lời một phần, hãy nói khéo: "Chưa thấy trong tài liệu" và gợi ý học sinh hỏi giáo viên.

Trả về JSON hợp lệ đúng dạng: {"lesson_md": "..."}
KHÔNG thêm chữ ngoài JSON.
"""

    user = {
        "day_title": (day_title or "Bài học").strip(),
        "level": (level or "beginner").strip().lower(),
        "objectives": objectives or [],
        "outline": outline or [],
        "evidence_chunks": packed,
    }

    try:
        data = chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.25,
            max_tokens=1400,
        )
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    lesson = str(data.get("lesson_md") or "").strip()
    if len(lesson) < 80:
        return None
    return lesson


def _generate_day_mcq_questions(
    *,
    topic: str,
    level: str,
    question_count: int,
    evidence_chunks: List[Dict[str, Any]],
    id_prefix: str,
    original_exercises: List[Dict[str, Any]] | None = None,
) -> List[HomeworkMCQQuestion]:
    """Generate small MCQ questions for daily homework (grounded to the same evidence).

    Uses the existing RAG-grounded quiz generators.
    """

    qc = max(0, int(question_count or 0))
    if qc <= 0:
        return []

    out_from_original: List[HomeworkMCQQuestion] = []
    for i, ex in enumerate(original_exercises or []):
        if not isinstance(ex, dict):
            continue
        stem = _compact(str(ex.get("question") or ""))
        if not stem:
            continue
        qid = f"{id_prefix}_orig_{i+1}"
        out_from_original.append(
            HomeworkMCQQuestion(
                question_id=qid,
                stem=stem,
                options=["A. Đúng", "B. Sai", "C. Chưa đủ dữ kiện", "D. Không liên quan"],
                correct_index=0,
                explanation=_compact(str(ex.get("answer_hint") or "")) or None,
                hint="Đọc lại ví dụ gốc trong tài liệu trước khi chọn đáp án.",
                related_concept=_compact(str(topic or "")) or None,
                max_points=1,
                sources=[],
            )
        )
        if len(out_from_original) >= qc:
            break
    if out_from_original:
        return out_from_original

    if not evidence_chunks:
        return []

    try:
        # Imported here to avoid importing the huge quiz_service module unless needed.
        from app.services.quiz_service import _generate_mcq_from_chunks, clean_mcq_questions

        raw = _generate_mcq_from_chunks(topic=str(topic or "tài liệu"), level=str(level or "beginner"), question_count=qc, chunks=evidence_chunks)
        cleaned = clean_mcq_questions(raw or [], limit=qc)
    except Exception:
        cleaned = []

    out: List[HomeworkMCQQuestion] = []
    for i, q in enumerate(cleaned or []):
        if not isinstance(q, dict):
            continue
        if (q.get("type") or "").lower() != "mcq":
            continue
        stem = _compact(str(q.get("stem") or ""))
        opts = q.get("options") or []
        try:
            ci = int(q.get("correct_index"))
        except Exception:
            ci = -1
        if not stem or not isinstance(opts, list) or len(opts) < 4 or ci < 0:
            continue

        qid = f"{id_prefix}_mcq_{i+1}"
        try:
            out.append(
                HomeworkMCQQuestion(
                    question_id=qid,
                    question_text=stem,
                    stem=stem,
                    options=[str(x) for x in opts][:4],
                    correct_index=int(ci),
                    explanation=_compact(str(q.get("explanation") or "")) or None,
                    hint=_compact(str(q.get("hint") or "")) or None,
                    related_concept=_compact(str(q.get("related_concept") or q.get("topic") or "")) or None,
                    bloom_level=str(q.get("bloom_level") or "remember"),
                    max_points=1,
                    sources=(q.get("sources") or []),
                )
            )
        except Exception:
            continue

    return out



def build_teacher_learning_plan(
    db: Session,
    *,
    user_id: int,
    teacher_id: int | None = None,
    level: str,
    assigned_topic: Optional[str],
    modules: List[LearningModule],
    days: int = 7,
    minutes_per_day: int = 35,
) -> TeacherLearningPlan:
    """Create a teacher-style daily plan (default 7 days).

    **Teacher-topics mode (requested):**
    - If the DB has `document_topics` (auto-extracted topics from teacher documents),
      the plan follows the *table-of-contents order* (topic_index) instead of a weakness-based order.

    Grounding:
    - Reading/homework are grounded to evidence chunks (document chunks).
    - Homework prompts are generated from evidence chunks when LLM is available; otherwise deterministic templates.
    """

    d = _cap_int(days, default=int(getattr(settings, "LEARNING_PLAN_DAYS", 7) or 7), lo=3, hi=14)
    mpd = _cap_int(
        minutes_per_day,
        default=int(getattr(settings, "LEARNING_PLAN_MINUTES_PER_DAY", 35) or 35),
        lo=15,
        hi=120,
    )

    # normalize module list
    mods: List[LearningModule] = []
    for m in (modules or []):
        if isinstance(m, LearningModule):
            mods.append(m)
        elif isinstance(m, dict):
            try:
                mods.append(LearningModule(**m))
            except Exception:
                continue

    plan_mode = _mode(getattr(settings, "LEARNING_PLAN_MODE", "auto"), default="auto")

    # 1) Prefer teacher topics (document_topics) when possible
    teacher_units = []
    try:
        teacher_units = _fetch_teacher_topic_units(
            db,
            assigned_topic=assigned_topic,
            modules=mods,
            preferred_user_id=int(teacher_id) if teacher_id is not None else None,
            max_docs=2,
        )
    except Exception:
        teacher_units = []

    wants_teacher = plan_mode in {"teacher_topics", "teacher", "toc", "outline", "curriculum", "syllabus"}
    use_teacher = wants_teacher or (plan_mode == "auto" and bool(teacher_units))

    # Fallback units from modules (when document_topics unavailable)
    if not use_teacher or not teacher_units:
        # Use module order (typically weak topics order) as fallback
        topics = [m.topic for m in mods if (m.topic or "").strip()]
        topics = list(dict.fromkeys([t.strip() for t in topics if t.strip()]))
        if not topics and assigned_topic:
            topics = [assigned_topic]

        m_by_topic = {m.topic: m for m in mods if (m.topic or "").strip()}
        units = []
        for t in topics:
            m = m_by_topic.get(t)
            units.append(
                {
                    "title": t,
                    "document_id": None,
                    "topic_index": None,
                    "summary": "",
                    "keywords": [],
                    "chunk_ids": list(getattr(m, "evidence_chunk_ids", []) or [])[:10] if m else [],
                    "lesson_md": (m.lesson_md if m else None),
                }
            )
        teacher_units = units
        use_teacher = False

    # At this point, teacher_units is our ordered syllabus.
    units = teacher_units
    n = len(units)
    if n <= 0:
        # ultra-fallback
        units = [{"title": assigned_topic or "tài liệu", "chunk_ids": [], "summary": "", "keywords": [], "lesson_md": None, "document_id": None, "topic_index": None}]
        n = 1

    # Split units into 1..5 content days, keep day6 review, day7 checkpoint (if present)
    content_days = min(max(1, d - 2), 5)
    content_days = min(content_days, n)  # don't exceed topic count

    base, rem = divmod(n, content_days)
    sizes = [base + (1 if i < rem else 0) for i in range(content_days)]
    # ensure no zero-sized group
    sizes = [s for s in sizes if s > 0]
    content_days = len(sizes) or 1

    day_units: Dict[int, List[int]] = {}
    idx = 0
    for day in range(1, content_days + 1):
        sz = sizes[day - 1]
        day_units[day] = list(range(idx, min(n, idx + sz)))
        idx += sz

    # day6 review, day7 checkpoint
    if d >= 6:
        day_units[6] = list(range(0, n))
    if d >= 7:
        day_units[7] = list(range(0, n))

    plan_days: List[LearningPlanDay] = []

    # helper to pick evidence chunk ids for a day
    def _evidence_for_indices(ixs: List[int], *, limit_ids: int = 8) -> List[int]:
        ids: List[int] = []
        for i in ixs:
            try:
                ids.extend([int(x) for x in (units[i].get("chunk_ids") or []) if isinstance(x, int)])
            except Exception:
                continue
        # de-dup
        out = list(dict.fromkeys(ids))[:limit_ids]
        return out

    # titles list (for review payload)
    all_titles = [u.get("title") for u in units if (u.get("title") or "").strip()]

    for day in range(1, d + 1):
        ixs = day_units.get(day, [])
        ulist = [units[i] for i in ixs if 0 <= i < len(units)]

        # --- Day header (1 lesson/day, 1 homework/day) ---
        if day == 6 and d >= 6:
            title = f"Bài {day}: Ôn tập theo mục lục" if use_teacher else f"Bài {day}: Ôn tập & củng cố"
            objectives = [
                "Tổng hợp lại kiến thức theo đúng thứ tự mục lục.",
                "Làm trắc nghiệm ôn tập để phát hiện lỗ hổng.",
                "Làm tự luận tổng hợp ngắn theo rubric."
            ]
            mcq_count = 8
        elif day == 7 and d >= 7:
            title = f"Bài {day}: Kiểm tra cuối tuần"
            objectives = [
                "Làm bài kiểm tra tổng hợp (trắc nghiệm + tự luận).",
                "Xem lại câu sai và ghi rút kinh nghiệm.",
                "Hoàn thiện bài tự luận tổng kết."
            ]
            mcq_count = 10
        else:
            main_u = ulist[0] if ulist else (units[0] if units else {"title": assigned_topic or "tài liệu"})
            main_t = (main_u.get("title") or assigned_topic or "tài liệu").strip()
            title = f"Bài {day}: {main_t}"
            objectives = [
                f"Nắm được nội dung trọng tâm của '{main_t}'.",
                "Làm đúng trắc nghiệm kiểm tra hiểu bài.",
                "Trả lời tự luận ngắn theo rubric."
            ]
            if len(ulist) > 1:
                objectives.append("(Tuỳ chọn) Học thêm 1 mục liền kề nếu còn thời gian.")

            # MCQ count scales a bit with level
            mcq_count = 4
            if str(level or "").lower().strip() == "advanced":
                mcq_count = 5
            if str(level or "").lower().strip() == "beginner":
                mcq_count = 4

        # Homework prompt (grounded)
        evidence_ids = _evidence_for_indices(ixs if ixs else list(range(0, n)), limit_ids=10)
        evidence_chunks = _fetch_chunks(db, evidence_ids)

        outline = []
        for u in (ulist or [])[:5]:
            if not isinstance(u, dict):
                continue
            outline.append({"title": u.get("title"), "summary": u.get("summary"), "keywords": u.get("keywords") or []})

        # Daily "textbook" lesson
        lesson_md = _llm_day_lesson(
            day_title=title,
            level=level,
            objectives=objectives,
            outline=outline,
            evidence_chunks=evidence_chunks,
        )
        if not lesson_md:
            lesson_md = _offline_day_lesson(
                day_title=title,
                level=level,
                objectives=objectives,
                outline=outline,
                evidence_chunks=evidence_chunks,
            )

        hw_topic = (ulist[0].get("title") if ulist else (assigned_topic or units[0].get("title") or "tài liệu"))
        hw_topic = (hw_topic or "tài liệu").strip()

        hw = _llm_homework(
            hw_topic,
            level=level,
            max_points=int(getattr(settings, "HOMEWORK_MAX_POINTS", 10) or 10),
            evidence_chunks=evidence_chunks,
        )
        if hw is None:
            hw = _offline_homework(
                hw_topic,
                level=level,
                max_points=int(getattr(settings, "HOMEWORK_MAX_POINTS", 10) or 10),
                sources=evidence_ids,
            )

        # MCQ bundled into homework (so we can remove the separate quiz UI)
        mcq_qs = _generate_day_mcq_questions(
            topic=hw_topic,
            level=level,
            question_count=int(mcq_count),
            evidence_chunks=evidence_chunks,
            id_prefix=f"d{int(day)}",
            original_exercises=(ulist[0].get("original_exercises") if ulist and isinstance(ulist[0], dict) else []),
        )
        try:
            hw = hw.model_copy(update={"mcq_questions": [q.model_dump() for q in (mcq_qs or [])]})
        except Exception:
            pass

        # Tasks: keep it teacher-like and simple (1 lesson + 1 homework).
        tasks: List[LearningPlanTask] = []
        tasks.append(
            LearningPlanTask(
                type="read",
                title="📘 Đọc bài học (1 bài/ngày)",
                instructions="Đọc kỹ bài học bên dưới như sách giáo khoa. Ghi lại 3 ý chính + 1 lỗi thường gặp.",
                estimated_minutes=max(10, mpd // 2),
                payload={"kind": "daily_lesson"},
            )
        )
        tasks.append(
            LearningPlanTask(
                type="homework",
                title="🏠 Bài tập về nhà (trắc nghiệm + tự luận)",
                instructions="Làm hết trắc nghiệm và tự luận. Nộp để nhận điểm + nhận xét chi tiết.",
                estimated_minutes=max(10, mpd - max(10, mpd // 2)),
                payload={"kind": "mixed_homework", "mcq_count": len(mcq_qs or [])},
            )
        )

        plan_days.append(
            LearningPlanDay(
                day_index=int(day),
                title=title,
                objectives=objectives,
                recommended_minutes=mpd,
                lesson_md=lesson_md,
                tasks=tasks,
                homework=hw,
            )
        )

    summary = (
        "Lộ trình kiểu giáo viên: mỗi ngày học 1 bài như sách giáo khoa + làm 1 bộ bài tập về nhà (trắc nghiệm + tự luận). "
        "Bài tập được chấm điểm ngay (MCQ tự chấm, tự luận chấm theo rubric). "
        "Ngày 6 ôn tập theo mục lục; ngày 7 kiểm tra tổng hợp (vẫn làm ngay trong bài tập về nhà)."
    )

    return TeacherLearningPlan(days=plan_days, summary=summary, days_total=d, minutes_per_day=mpd)
