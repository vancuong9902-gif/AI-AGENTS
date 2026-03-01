from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent_log import AgentLog
from app.models.classroom import ClassroomMember
from app.models.document import Document
from app.models.document_topic import DocumentTopic
from app.models.learning_plan import LearningPlan
from app.models.session import Session as UserSession
from app.schemas.tutor import TutorChatData, TutorGenerateQuestionsData
from app.services.embedding_service import embed_texts
from app.services.user_service import ensure_user_exists
from app.services.corrective_rag import corrective_retrieve_and_log
from app.services.rag_service import auto_document_ids_for_query
from app.services.text_quality import filter_chunks_by_quality
from app.services.llm_service import llm_available, chat_json, chat_text, pack_chunks
from app.services.quiz_service import clean_mcq_questions, _generate_mcq_from_chunks
from app.services.topic_service import build_topic_details

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


TUTOR_REFUSAL_TEMPLATE = (
    "Xin lỗi, tôi chỉ có thể hỗ trợ các câu hỏi liên quan đến [{scope}]. "
    "Câu hỏi này nằm ngoài phạm vi tôi có thể giải đáp. Bạn có muốn hỏi về [{scope}] không?"
)

TUTOR_SYSTEM_PROMPT = """Bạn là AI Tutor cho học sinh.

INPUT
- question
- current_topic (optional)
- evidence_chunks (đã retrieve + rerank)
- relevance_score (0..1)

LUẬT PHẠM VI
- Nếu relevance_score < ngưỡng hoặc evidence không đủ: từ chối lịch sự, nói rõ “ngoài phạm vi tài liệu hiện tại”, gợi ý cách hỏi lại + đưa ra 3 câu hỏi liên quan trong phạm vi.
- Nếu đủ evidence: giải thích như giáo viên:
  1) trả lời ngắn 1–2 câu
  2) giải thích chi tiết theo bước
  3) ví dụ (nếu không có trong evidence thì ghi “ví dụ minh hoạ giả định”)
  4) lỗi thường gặp
  5) tóm tắt 3 ý

RÀNG BUỘC
- Chỉ dùng thông tin có trong evidence_chunks; không bịa.
- Nếu câu hỏi ngoài chủ đề: trả về refuse_out_of_scope.
- Nếu text nguồn quá nhiễu/thiếu để trả lời an toàn: trả về need_clean_text.
- Luôn trả JSON hợp lệ theo đúng schema được yêu cầu ở user message.

PHẠM VI CHỦ ĐỀ HIỆN TẠI: {topic_scope}
TÓM TẮT CÂU HỎI HỌC SINH: {user_question_summary}

CONTEXT (Tài liệu học):
{rag_context}
"""

class OffTopicDetector:
    """Multi-layer off-topic detection cho Tutor AI."""

    ALWAYS_REJECT_PATTERNS = [
        r"hãy\s+làm\s+(bài|giúp|thay)",
        r"cho\s+tôi\s+đáp\s+án\s+câu",
        r"(thời\s*tiết|tin\s*tức|bóng\s*đá|giải\s*trí)",
        r"(hack|crack|bypass|cheat)",
        r"(viết\s+code|lập\s+trình)",
    ]

    def check(self, question: str, topic: str, rag_results: dict) -> dict:
        for pattern in self.ALWAYS_REJECT_PATTERNS:
            if re.search(pattern, question or "", re.IGNORECASE):
                return {
                    "is_off_topic": True,
                    "reason": "keyword_blacklist",
                    "confidence": 0.99,
                    "layer": 1,
                }

        best_relevance = self._get_rag_relevance(rag_results)
        if best_relevance < 0.1:
            return {
                "is_off_topic": True,
                "reason": "low_rag_relevance",
                "confidence": 1 - best_relevance,
                "layer": 2,
            }

        if 0.1 <= best_relevance < 0.3 and llm_available():
            llm_verdict = self._llm_topic_check(question=question, topic=topic)
            if not llm_verdict:
                return {
                    "is_off_topic": True,
                    "reason": "llm_classification",
                    "confidence": 0.85,
                    "layer": 3,
                }

        return {
            "is_off_topic": False,
            "reason": None,
            "confidence": best_relevance,
            "layer": 0,
        }

    def _get_rag_relevance(self, rag_results: dict) -> float:
        corr = rag_results.get("corrective") or {}
        attempts = corr.get("attempts") or []
        if attempts:
            return float(attempts[-1].get("best_relevance", 0.0) or 0.0)
        return 0.0

    def _llm_topic_check(self, question: str, topic: str) -> bool:
        prompt = (
            f"Phân loại câu hỏi sau:\n"
            f"Câu hỏi: \"{(question or '')[:200]}\"\n"
            f"Chủ đề học: \"{topic or ''}\"\n\n"
            "Câu hỏi có liên quan đến chủ đề học KHÔNG?\n"
            "Trả lời: YES (có liên quan) hoặc NO (không liên quan)"
        )
        try:
            resp = chat_text(messages=[{"role": "user", "content": prompt}], max_tokens=10, temperature=0)
        except Exception:
            return True
        return "yes" in (resp or "").lower()


_off_topic_detector = OffTopicDetector()

_LOCAL_SESSION_STORE: Dict[str, Dict[str, Any]] = {}
_TOPIC_GATE_CACHE: Dict[str, Dict[str, Any]] = {}
_OFFTOPIC_GATE_CACHE: Dict[str, Dict[str, Any]] = {}
_OFFTOPIC_GATE_CACHE_TTL_SEC = 30 * 60


def _offtopic_gate_cache_key(question: str, topic: Optional[str], document_ids: Optional[List[int]]) -> str:
    raw = json.dumps(
        {
            "q": (question or "").strip().lower(),
            "topic": (topic or "").strip().lower(),
            "doc_ids": sorted({int(x) for x in (document_ids or []) if x is not None}),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_question_on_topic_llm(
    db: Session,
    question: str,
    topic: Optional[str],
    document_ids: Optional[List[int]],
) -> tuple[bool, str, Optional[str]]:
    cache_key = _offtopic_gate_cache_key(question, topic, document_ids)
    now = time.time()
    cached = _OFFTOPIC_GATE_CACHE.get(cache_key)
    if cached and float(cached.get("expires_at", 0.0) or 0.0) > now:
        return bool(cached.get("is_on_topic", True)), str(cached.get("reason") or "cached"), cached.get("matched_topic")

    if not llm_available():
        raise RuntimeError("llm_not_available")

    ids = sorted({int(x) for x in (document_ids or []) if x is not None})
    doc_titles = []
    if ids:
        doc_titles = [
            str(title or "").strip()
            for (title,) in db.query(Document.title).filter(Document.id.in_(ids)).all()
            if str(title or "").strip()
        ]

    topic_rows = (
        db.query(DocumentTopic.title, DocumentTopic.keywords, DocumentTopic.summary, DocumentTopic.extraction_confidence)
        .filter(DocumentTopic.document_id.in_(ids))
        .order_by(DocumentTopic.extraction_confidence.desc(), DocumentTopic.id.asc())
        .limit(30)
        .all()
        if ids
        else []
    )

    topic_hint = (topic or "").strip()
    selected_topics: List[Dict[str, str]] = []
    if topic_hint:
        topic_lower = topic_hint.lower()
        preferred = [r for r in topic_rows if topic_lower in str((r[0] or "")).lower()]
        others = [r for r in topic_rows if r not in preferred]
        ordered = preferred + others
    else:
        ordered = list(topic_rows)

    for row in ordered[:5]:
        title = str((row[0] or "")).strip()
        keywords = row[1] or []
        summary = str((row[2] or "")).strip()
        kw = ", ".join([str(k).strip() for k in keywords if str(k).strip()][:8])
        selected_topics.append({"title": title, "keywords": kw, "summary": summary[:280]})

    payload = {
        "question": (question or "").strip(),
        "preferred_topic": topic_hint or None,
        "document_titles": doc_titles[:10],
        "document_topics": selected_topics,
    }

    resp = chat_json(
        messages=[
            {
                "role": "system",
                "content": (
                    "Bạn là bộ lọc on-topic cho AI Tutor. "
                    "Nhiệm vụ: phân loại câu hỏi có thuộc phạm vi kiến thức tài liệu hay không. "
                    "Quy tắc: câu hỏi đời sống, giải trí, tin tức, cá nhân => off-topic. "
                    "Câu hỏi xin ví dụ thực tế áp dụng kiến thức có trong tài liệu => on-topic. "
                    "Trả về STRICT JSON duy nhất, không markdown, không text thừa, đúng schema: "
                    '{"is_on_topic":true,"reason":"<30 từ>","matched_topic":"..."}. '
                    "matched_topic có thể null nếu không xác định."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=180,
    )

    if not isinstance(resp, dict):
        raise RuntimeError("invalid_llm_response")

    is_on_topic = bool(resp.get("is_on_topic", False))
    reason = str(resp.get("reason") or "").strip() or "llm_gate"
    matched_topic_raw = resp.get("matched_topic")
    matched_topic = str(matched_topic_raw).strip() if matched_topic_raw is not None else None
    if matched_topic == "":
        matched_topic = None

    _OFFTOPIC_GATE_CACHE[cache_key] = {
        "is_on_topic": is_on_topic,
        "reason": reason,
        "matched_topic": matched_topic,
        "expires_at": now + _OFFTOPIC_GATE_CACHE_TTL_SEC,
    }
    return is_on_topic, reason, matched_topic


def _session_key(user_id: int) -> str:
    return f"tutor:session:{int(user_id)}"


def _get_redis_client():
    if redis is None:
        return None
    try:
        return redis.Redis.from_url(str(getattr(settings, "REDIS_URL", "redis://localhost:6379/0")), decode_responses=True)
    except Exception:
        return None


def _load_tutor_session(user_id: int) -> Dict[str, Any]:
    key = _session_key(user_id)
    cli = _get_redis_client()
    if cli is not None:
        try:
            raw = cli.get(key)
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return dict(_LOCAL_SESSION_STORE.get(key) or {"recent_questions": [], "explained_topics": []})


def _save_tutor_session(user_id: int, data: Dict[str, Any], ttl_sec: int = 60 * 60 * 24) -> None:
    key = _session_key(user_id)
    payload = dict(data or {})
    _LOCAL_SESSION_STORE[key] = payload
    cli = _get_redis_client()
    if cli is not None:
        try:
            cli.setex(key, int(ttl_sec), json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass


def _topic_gate_cache_key(*, question: str, topic: Optional[str], document_ids: Optional[List[int]]) -> str:
    ids = [str(int(x)) for x in (document_ids or []) if x is not None]
    ids.sort()
    raw = f"{(question or '').strip().lower()}|{(topic or '').strip().lower()}|{','.join(ids)}"
    return f"tutor:topic_gate:{raw}"


def _topic_gate_cache_get(key: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    cli = _get_redis_client()
    if cli is not None:
        try:
            raw = cli.get(key)
            if raw:
                val = json.loads(raw)
                if isinstance(val, dict):
                    return val
        except Exception:
            pass
    local = _TOPIC_GATE_CACHE.get(key)
    if not isinstance(local, dict):
        return None
    if float(local.get("expires_at", 0.0) or 0.0) <= now:
        _TOPIC_GATE_CACHE.pop(key, None)
        return None
    out = dict(local)
    out.pop("expires_at", None)
    return out


def _topic_gate_cache_set(key: str, value: Dict[str, Any], ttl_sec: int = 60 * 30) -> None:
    payload = dict(value or {})
    payload.pop("expires_at", None)
    cli = _get_redis_client()
    if cli is not None:
        try:
            cli.setex(key, int(ttl_sec), json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass
    _TOPIC_GATE_CACHE[key] = {**payload, "expires_at": time.time() + int(ttl_sec)}


def _topic_lexical_overlap(question: str, topic: Optional[str], context_lines: List[str]) -> bool:
    q_tokens = _tokenize_vi(question)
    if not q_tokens:
        return True
    scope_tokens = _tokenize_vi(" ".join([topic or "", *context_lines]))
    if not scope_tokens:
        return True
    overlap = len(q_tokens & scope_tokens)
    return overlap >= 2 or (overlap >= 1 and len(q_tokens) <= 5)


def _is_question_on_topic_llm(db: Session, *, question: str, topic: Optional[str], document_ids: Optional[List[int]]) -> Dict[str, Any]:
    cache_key = _topic_gate_cache_key(question=question, topic=topic, document_ids=document_ids)
    cached = _topic_gate_cache_get(cache_key)
    if cached:
        return cached

    doc_ids = [int(x) for x in (document_ids or []) if x is not None]
    docs = db.query(Document.id, Document.title).filter(Document.id.in_(doc_ids)).limit(8).all() if doc_ids else []
    topic_rows = (
        db.query(DocumentTopic.title, DocumentTopic.summary, DocumentTopic.keywords)
        .filter(DocumentTopic.document_id.in_(doc_ids))
        .order_by(DocumentTopic.extraction_confidence.desc())
        .limit(5)
        .all()
        if doc_ids
        else []
    )
    context_lines: List[str] = []
    for _, title in docs:
        if str(title or "").strip():
            context_lines.append(f"Document: {str(title).strip()}")
    for t_title, summary, keywords in topic_rows[:5]:
        kw = ", ".join([str(x).strip() for x in (keywords or []) if str(x).strip()][:8])
        context_lines.append(
            f"Topic: {str(t_title or '').strip()} | Summary: {str(summary or '').strip()[:220]} | Keywords: {kw}"
        )

    fallback = {
        "is_on_topic": _topic_lexical_overlap(question, topic, context_lines),
        "reason": "lexical_fallback",
        "suggested_questions": _suggest_on_topic_questions(topic, question),
    }

    if not (settings.TUTOR_LLM_OFFTOPIC_ENABLED and llm_available()):
        _topic_gate_cache_set(cache_key, fallback)
        return fallback

    try:
        llm_resp = chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là bộ phân loại on-topic cho AI Tutor. "
                        "Bạn PHẢI trả về STRICT JSON với đúng schema: "
                        "{\"is_on_topic\": true|false, \"reason\": \"string\", \"suggested_questions\": [\"string\",\"string\",\"string\"]}. "
                        "Không trả thêm text ngoài JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": question,
                            "topic": _topic_scope(topic),
                            "document_ids": doc_ids,
                            "scope_context": context_lines[:8],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=220,
        )
        verdict = {
            "is_on_topic": bool((llm_resp or {}).get("is_on_topic", True)),
            "reason": str((llm_resp or {}).get("reason") or "llm_topic_gate"),
            "suggested_questions": [
                str(x).strip() for x in ((llm_resp or {}).get("suggested_questions") or []) if str(x).strip()
            ][:3],
        }
        if not verdict["suggested_questions"]:
            verdict["suggested_questions"] = _suggest_on_topic_questions(topic, question)
        _topic_gate_cache_set(cache_key, verdict)
        return verdict
    except Exception:
        fallback["reason"] = "lexical_fallback_after_llm_error"
        _topic_gate_cache_set(cache_key, fallback)
        return fallback


def _suggest_topics(db: Session, *, document_ids: Optional[List[int]], top_k: int = 3) -> List[str]:
    ids = [int(x) for x in (document_ids or []) if x is not None]
    if not ids:
        return []
    rows = (
        db.query(DocumentTopic.display_title, DocumentTopic.title, func.max(DocumentTopic.extraction_confidence).label("conf"))
        .filter(DocumentTopic.document_id.in_(ids))
        .group_by(DocumentTopic.display_title, DocumentTopic.title)
        .order_by(func.max(DocumentTopic.extraction_confidence).desc())
        .limit(int(max(1, top_k)))
        .all()
    )
    out: List[str] = []
    for display_title, title, _ in rows:
        val = str(display_title or title or "").strip()
        if val and val not in out:
            out.append(val)
    return out[:top_k]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    na = math.sqrt(sum(float(x) * float(x) for x in a))
    nb = math.sqrt(sum(float(y) * float(y) for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return float(dot / (na * nb))


def _intent_aware_topic_suggestions(
    db: Session,
    *,
    question: str,
    topic: Optional[str],
    document_ids: Optional[List[int]],
    top_k: int = 3,
) -> List[str]:
    approved = _suggest_topics(db, document_ids=document_ids, top_k=15)
    if not approved:
        scope = _topic_scope(topic)
        return [scope]
    try:
        vectors = embed_texts([question] + approved)
        if not isinstance(vectors, list) or len(vectors) != len(approved) + 1:
            return approved[:top_k]
        qv = vectors[0]
        scored: List[tuple[float, str]] = []
        for i, name in enumerate(approved, start=1):
            scored.append((_cosine_similarity(qv, vectors[i]), name))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [name for _, name in scored[: max(1, int(top_k))]]
    except Exception:
        return approved[:top_k]


def _build_off_topic_message(*, scope: str, approved_topics: List[str], suggestions: List[str]) -> str:
    return TUTOR_REFUSAL_TEMPLATE.format(scope=scope)


def _suggest_on_topic_questions(topic: Optional[str], off_topic_q: str) -> List[str]:
    scope = (topic or "chủ đề học hiện tại").strip()
    if not scope:
        scope = "chủ đề học hiện tại"

    topic_lower = scope.lower()
    if "phương trình bậc hai" in topic_lower:
        return [
            "Công thức nghiệm của phương trình bậc hai là gì?",
            "Khi nào phương trình bậc hai vô nghiệm?",
            "Ứng dụng của phương trình bậc hai trong thực tế?",
        ]

    return [
        f"Khái niệm cốt lõi của '{scope}' là gì?",
        f"Những lỗi thường gặp khi học '{scope}' là gì?",
        f"Bạn có thể cho một ví dụ áp dụng của '{scope}' không?",
    ]


def _llm_offtopic_gate(*, question: str, topic: Optional[str], evidence_previews: List[str]) -> Dict[str, Any]:
    default = {"status": "in_scope", "confidence": 0.0, "reason": "gate_disabled"}
    if not (settings.TUTOR_LLM_OFFTOPIC_ENABLED and llm_available()):
        return default

    scope = _topic_scope(topic)
    payload = {
        "question": question,
        "topic_scope": scope,
        "evidence_previews": [str(x).strip() for x in (evidence_previews or []) if str(x).strip()][:6],
    }
    try:
        resp = chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là bộ lọc phạm vi cho AI Tutor. "
                        "Dựa vào topic_scope và evidence_previews để xác định câu hỏi có nằm trong phạm vi hay không. "
                        "Chỉ trả về JSON hợp lệ, dùng double quotes, đúng schema: "
                        "{\"status\":\"in_scope|uncertain|out_of_scope\",\"confidence\":0.0,\"reason\":\"...\"}. "
                        "Nếu thiếu bằng chứng hoặc câu hỏi mơ hồ thì chọn uncertain."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=140,
        )
        status = str((resp or {}).get("status") or "").strip().lower()
        if status not in {"in_scope", "uncertain", "out_of_scope"}:
            return default
        try:
            confidence = float((resp or {}).get("confidence", 0.0) or 0.0)
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        reason = str((resp or {}).get("reason") or "").strip() or "llm_gate"
        return {"status": status, "confidence": confidence, "reason": reason}
    except Exception:
        return default


def _normalize_follow_up_questions(topic: Optional[str], suggestions: List[str]) -> List[str]:
    out = [str(x).strip() for x in (suggestions or []) if str(x).strip()]
    scope = _topic_scope(topic)
    defaults = [
        f"Bạn muốn mình tóm tắt nhanh ý chính của {scope} không?",
        f"Bạn muốn mình đưa thêm ví dụ áp dụng của {scope} không?",
        f"Bạn còn câu hỏi nào về {scope} không?",
    ]
    for q in defaults:
        if q not in out:
            out.append(q)
    return out[:3]


def _extract_sources_used(sources: List[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    for s in sources or []:
        title = str((s or {}).get("document_title") or "").strip()
        if title and title not in names:
            names.append(title)
    return names[:5]


def _extract_referenced_topic(question: str) -> str:
    s = (question or "").strip()
    m = re.search(r"(?:topic|chủ đề)\s+(.+)$", s, flags=re.I)
    if m:
        return m.group(1).strip(" .,:;")
    return s[:120].strip()


def _related_homework_links(db: Session, *, user_id: int, topic: Optional[str], limit: int = 2) -> List[Dict[str, str]]:
    rows = (
        db.query(LearningPlan)
        .filter(LearningPlan.user_id == int(user_id))
        .order_by(LearningPlan.created_at.desc())
        .limit(3)
        .all()
    )
    if not rows:
        return []
    t = (topic or "").lower().strip()
    out: List[Dict[str, str]] = []
    for lp in rows:
        plan = lp.plan_json if isinstance(lp.plan_json, dict) else {}
        days = plan.get("days") if isinstance(plan, dict) else []
        if not isinstance(days, list):
            continue
        for d in days:
            if not isinstance(d, dict):
                continue
            title = str(d.get("title") or "").strip()
            hw = d.get("homework") if isinstance(d.get("homework"), dict) else {}
            stem = str(hw.get("stem") or "").strip()
            hay = f"{title} {stem}".lower()
            if t and (t not in hay):
                continue
            day_index = d.get("day_index")
            try:
                day_int = int(day_index)
            except Exception:
                continue
            out.append(
                {
                    "title": f"Bài tập ngày {day_int}: {title or 'Ôn tập'}",
                    "url": f"/learning-plans/{int(lp.id)}/homework/{int(user_id)}/{day_int}",
                }
            )
            if len(out) >= int(limit):
                return out
    return out[:limit]


def _append_topic_aware_section(
    answer_md: str,
    *,
    topic: Optional[str],
    follow_ups: List[str],
    homework_links: List[Dict[str, str]],
) -> str:
    qlist = [x.strip() for x in (follow_ups or []) if x and x.strip()][:3]
    if len(qlist) < 2:
        scope = _topic_scope(topic)
        qlist.extend(
            [
                f"Khái niệm cốt lõi nào trong {scope} bạn còn thấy mơ hồ?",
                f"Bạn muốn luyện một bài tập ngắn về {scope} không?",
            ]
        )
    qlist = qlist[:3]
    link_lines = [f"- [{it.get('title')}]({it.get('url')})" for it in homework_links if it.get("url")][:2]
    links_md = "\n".join(link_lines) if link_lines else "- Chưa có link bài tập phù hợp trong learning plan hiện tại."
    suggest_md = "\n".join([f"- {x}" for x in qlist])
    return (
        (answer_md or "").rstrip()
        + "\n\n---\n"
        + "### 💡 Xem thêm\n"
        + "**Câu hỏi gợi ý liên quan:**\n"
        + f"{suggest_md}\n\n"
        + "**Bài tập liên quan:**\n"
        + f"{links_md}"
    )


def _log_tutor_flagged_question(
    db: Session,
    *,
    user_id: int,
    question: str,
    topic: Optional[str],
    reason: str,
    suggested_topics: Optional[List[str]] = None,
):
    row = AgentLog(
        event_id=uuid.uuid4().hex,
        event_type="tutor_off_topic",
        agent_name="ai_tutor",
        user_id=int(user_id),
        input_payload={"question": question, "topic": topic},
        output_summary={
            "was_answered": False,
            "off_topic_reason": reason,
            "suggested_topics": suggested_topics or [],
        },
        status="success",
    )
    db.add(row)
    db.commit()


def get_classroom_tutor_logs(db: Session, *, classroom_id: int, flagged: bool = False) -> List[Dict[str, Any]]:
    student_ids = [
        int(uid)
        for (uid,) in db.query(ClassroomMember.user_id)
        .filter(ClassroomMember.classroom_id == int(classroom_id))
        .all()
    ]
    if not student_ids:
        return []

    q = db.query(AgentLog).filter(AgentLog.agent_name == "ai_tutor", AgentLog.user_id.in_(student_ids))
    if flagged:
        q = q.filter(AgentLog.event_type == "tutor_off_topic")
    rows = q.order_by(AgentLog.created_at.desc()).limit(200).all()

    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": int(row.id),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "user_id": int(row.user_id) if row.user_id is not None else None,
                "question": (row.input_payload or {}).get("question"),
                "topic": (row.input_payload or {}).get("topic"),
                "event_type": row.event_type,
                "was_answered": (row.output_summary or {}).get("was_answered"),
                "off_topic_reason": (row.output_summary or {}).get("off_topic_reason"),
                "suggested_topics": (row.output_summary or {}).get("suggested_topics") or [],
            }
        )
    return out


def _src_preview(text: str, n: int = 180) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _topic_scope(topic: Optional[str]) -> str:
    t = (topic or "").strip()
    return t or "môn học hiện tại"


def _build_redirect_hint(topic: Optional[str]) -> str:
    scope = _topic_scope(topic)
    try:
        samples = [
            f"Khái niệm cốt lõi trong {scope} là gì?",
            f"Bạn có thể giải thích một ví dụ điển hình của {scope} không?",
        ]
        sample_question = "' hoặc '".join(samples[:2])
        return f"Bạn có thể hỏi về '{scope}', ví dụ: '{sample_question}'"
    except Exception:
        return f"Bạn có thể hỏi về '{scope}', ví dụ: 'Khái niệm cốt lõi trong {scope} là gì?'"


def _tokenize_vi(text: str) -> set[str]:
    return {w for w in re.findall(r"[\wÀ-ỹ]+", (text or "").lower()) if len(w) >= 3}


def _is_practice_request(question: str) -> bool:
    q = (question or "").lower()
    return any(k in q for k in ["kiểm tra tôi", "practice with tutor", "đặt câu hỏi", "quiz tôi", "hỏi tôi về"])


def _generate_practice_question(topic: str, chunks: List[Dict[str, Any]]) -> str:
    if llm_available() and chunks:
        packed = pack_chunks(chunks, max_chunks=min(3, len(chunks)), max_chars_per_chunk=600, max_total_chars=1800)
        try:
            out = chat_json(
                messages=[
                    {"role": "system", "content": "Bạn là gia sư. Tạo 1 câu hỏi kiểm tra ngắn, rõ ràng, bám sát tài liệu. Trả JSON {stem:string}."},
                    {"role": "user", "content": json.dumps({"topic": topic, "evidence_chunks": packed}, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=180,
            )
            stem = str((out or {}).get("stem") or "").strip()
            if stem:
                return stem
        except Exception:
            pass
    t = (topic or "chủ đề này").strip()
    return f"Hãy nêu 2 ý quan trọng nhất của {t} và cho 1 ví dụ minh hoạ ngắn."


def _grade_practice_answer(*, topic: str, question: str, answer: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if llm_available() and chunks:
        packed = pack_chunks(chunks, max_chunks=min(3, len(chunks)), max_chars_per_chunk=600, max_total_chars=1800)
        try:
            out = chat_json(
                messages=[
                    {"role": "system", "content": "Bạn là gia sư chấm nhanh. Trả JSON {score:int(0|1), feedback:string, explanation:string}."},
                    {
                        "role": "user",
                        "content": json.dumps({"topic": topic, "question": question, "student_answer": answer, "evidence_chunks": packed}, ensure_ascii=False),
                    },
                ],
                temperature=0.0,
                max_tokens=280,
            )
            if isinstance(out, dict):
                return {
                    "score": int(1 if int(out.get("score", 0) or 0) > 0 else 0),
                    "feedback": str(out.get("feedback") or ""),
                    "explanation": str(out.get("explanation") or ""),
                }
        except Exception:
            pass
    ans_len = len((answer or "").strip())
    ok = 1 if ans_len >= 40 else 0
    return {
        "score": ok,
        "feedback": "Trả lời khá ổn." if ok else "Câu trả lời còn ngắn, cần bổ sung ý chính.",
        "explanation": "Hãy nêu rõ khái niệm chính, ví dụ và lưu ý sai thường gặp.",
    }


def tutor_chat(
    db: Session,
    *,
    user_id: int,
    question: str,
    topic: Optional[str] = None,
    top_k: int = 6,
    document_ids: Optional[List[int]] = None,
    allowed_topics: Optional[List[str]] = None,
    assessment_id: Optional[int] = None,
    attempt_id: Optional[int] = None,
    exam_mode: bool = False,
) -> Dict[str, Any]:
    """Virtual AI Tutor (RAG). Answers using only retrieved evidence and suggests follow-ups."""

    ensure_user_exists(db, int(user_id), role="student")

    q = (question or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="Missing question")

    active_exam = bool(exam_mode)
    if attempt_id is not None:
        attempt_row = db.query(UserSession).filter(UserSession.id == int(attempt_id), UserSession.user_id == int(user_id)).first()
        if attempt_row and str(attempt_row.type or "").startswith("quiz_attempt:") and attempt_row.ended_at is None and attempt_row.locked_at is None:
            active_exam = True
    elif assessment_id is not None:
        ar = db.query(UserSession).filter(
            UserSession.user_id == int(user_id),
            UserSession.type == f"quiz_attempt:{int(assessment_id)}",
            UserSession.ended_at.is_(None),
            UserSession.locked_at.is_(None),
        ).order_by(UserSession.id.desc()).first()
        active_exam = bool(ar)

    if active_exam:
        hint = "Mình đang ở chế độ hỗ trợ khi làm bài có giới hạn thời gian nên chỉ đưa gợi ý, không cung cấp đáp án trực tiếp.\n\nGợi ý: tóm tắt đề, xác định từ khóa/chủ điểm liên quan trong tài liệu, rồi thử tự lập dàn ý 2-3 bước trước khi chọn đáp án."
        return TutorChatData(
            answer_md=hint,
            was_answered=True,
            is_off_topic=False,
            refusal_reason="exam_mode_hint_only",
            follow_up_questions=["Bạn muốn mình gợi ý cách phân tích đề cho câu này?", "Bạn muốn kiểm tra lại các khái niệm liên quan trong tài liệu không?"],
            suggested_topics=[topic] if topic else [],
            quick_check_mcq=[],
            sources=[],
            retrieval={"exam_mode": True, "assessment_id": assessment_id, "attempt_id": attempt_id},
        ).model_dump()

    # Minimal tracking for tutor usage analytics.
    db.add(UserSession(user_id=int(user_id), type="tutor_chat"))
    db.commit()

    if allowed_topics and llm_available():
        topic_list = [str(t).strip() for t in allowed_topics if str(t).strip()][:10]
        if topic_list:
            topic_list_str = "\n".join(f"- {t}" for t in topic_list)
            classification_prompt = (
                f"Danh sách chủ đề học tập được phép:\n{topic_list_str}\n\n"
                f"Câu hỏi của học sinh: \"{q}\"\n\n"
                "Hãy trả lời CHỈ bằng JSON: {\"relevant\": true/false, \"matched_topic\": \"tên topic nếu có hoặc null\", \"reason\": \"lý do ngắn\"}\n"
                "Câu hỏi được coi là relevant nếu nó liên quan đến BẤT KỲ topic nào trong danh sách trên, "
                "hoặc là câu hỏi chung về cách học, phương pháp, hoặc xin giải thích khái niệm trong sách."
            )
            try:
                check_result = chat_json(
                    messages=[{"role": "user", "content": classification_prompt}],
                    temperature=0.0,
                    max_tokens=150,
                )
                is_relevant = bool((check_result or {}).get("relevant", True))
                if not is_relevant:
                    top = [str(t) for t in topic_list]
                    return {
                        "answer": (
                            "Xin lỗi bạn! Câu hỏi này có vẻ nằm ngoài phạm vi các chủ đề đang học. "
                            f"Hiện tại chúng ta đang tập trung vào: {', '.join(top[:3])}{'...' if len(top) > 3 else ''}. "
                            "Bạn có muốn hỏi điều gì về các chủ đề đó không? 😊"
                        ),
                        "off_topic": True,
                        "allowed_topics": top,
                        "sources": [],
                        "follow_up_questions": [
                            f"Bạn có thể giải thích về {top[0]}?",
                            f"Cho tôi ví dụ về {top[0]}?",
                        ] if top else [],
                    }
            except Exception:
                pass

    session = _load_tutor_session(int(user_id))
    recent_questions = [str(x).strip() for x in (session.get("recent_questions") or []) if str(x).strip()]
    explained_topics = [str(x).strip() for x in (session.get("explained_topics") or []) if str(x).strip()]

    doc_ids = list(document_ids or [])
    if not doc_ids:
        auto = auto_document_ids_for_query(db, topic or q, preferred_user_id=settings.DEFAULT_TEACHER_ID, max_docs=3)
        if auto:
            doc_ids = auto

    suggested_topics = _suggest_topics(db, document_ids=doc_ids, top_k=6)
    intent_suggestions = _intent_aware_topic_suggestions(db, question=q, topic=topic, document_ids=doc_ids, top_k=3)

    llm_gate_result: Optional[Dict[str, Any]] = None
    llm_gate_failed = False
    try:
        gate_on_topic, gate_reason, gate_matched_topic = _is_question_on_topic_llm(db, q, topic, doc_ids)
        llm_gate_result = {
            "is_on_topic": bool(gate_on_topic),
            "reason": str(gate_reason or "llm_gate"),
            "matched_topic": gate_matched_topic,
        }
        if not gate_on_topic:
            topic_label = topic or gate_matched_topic or "chủ đề học hiện tại"
            refusal = (
                f"Xin lỗi bạn, câu hỏi này có vẻ chưa thuộc phạm vi tài liệu/chủ đề đang học ({topic_label}). "
                "Mình có thể hỗ trợ rất tốt nếu bạn hỏi theo nội dung bài học nhé!"
            )
            _log_tutor_flagged_question(
                db,
                user_id=int(user_id),
                question=q,
                topic=topic,
                reason=str(gate_reason or "llm_off_topic"),
                suggested_topics=intent_suggestions,
            )
            return TutorChatData(
                answer_md=refusal,
                was_answered=False,
                is_off_topic=True,
                refusal_message=refusal,
                off_topic_reason=str(gate_reason or "llm_off_topic"),
                suggested_topics=intent_suggestions,
                follow_up_questions=_suggest_on_topic_questions(topic or gate_matched_topic, q),
                quick_check_mcq=[],
                sources=[],
                retrieval={"llm_topic_gate": llm_gate_result},
            ).model_dump()
    except Exception:
        llm_gate_failed = True

    practice = session.get("practice") if isinstance(session.get("practice"), dict) else {}
    if _is_practice_request(q) and not (practice.get("awaiting_answer")):
        p_topic = _extract_referenced_topic(q) or (topic or "chủ đề hiện tại")
        rag_p = corrective_retrieve_and_log(db=db, query=p_topic, top_k=6, filters={"document_ids": doc_ids} if doc_ids else {}, topic=p_topic)
        p_chunks = rag_p.get("chunks") or []
        stem = _generate_practice_question(p_topic, p_chunks)
        session["practice"] = {"active": True, "topic": p_topic, "score": int(practice.get("score", 0) or 0), "asked": int(practice.get("asked", 0) or 0) + 1, "awaiting_answer": True, "current_question": stem}
        session["recent_questions"] = (recent_questions + [q])[-5:]
        _save_tutor_session(int(user_id), session)
        return TutorChatData(
            answer_md=(f"🎯 **Practice with Tutor**\n\nCâu hỏi: {stem}\n\nBạn hãy trả lời, mình sẽ chấm và giải thích ngay."),
            was_answered=True,
            is_off_topic=False,
            refusal_message=None,
            suggested_topics=intent_suggestions,
            follow_up_questions=_normalize_follow_up_questions(topic, []),
            quick_check_mcq=[],
            sources=[],
            sources_used=[],
            confidence=0.9,
            retrieval={"mode": "practice_start"},
        ).model_dump()

    if practice.get("active") and practice.get("awaiting_answer"):
        p_topic = str(practice.get("topic") or topic or "chủ đề hiện tại")
        stem = str(practice.get("current_question") or "")
        rag_p = corrective_retrieve_and_log(db=db, query=p_topic, top_k=6, filters={"document_ids": doc_ids} if doc_ids else {}, topic=p_topic)
        grade = _grade_practice_answer(topic=p_topic, question=stem, answer=q, chunks=rag_p.get("chunks") or [])
        score = int(practice.get("score", 0) or 0) + int(grade.get("score", 0) or 0)
        asked = int(practice.get("asked", 1) or 1)
        session["practice"] = {"active": False, "topic": p_topic, "score": score, "asked": asked, "awaiting_answer": False, "current_question": None}
        db.add(AgentLog(event_id=uuid.uuid4().hex, event_type="tutor_practice_summary", agent_name="ai_tutor", user_id=int(user_id), input_payload={"topic": p_topic}, output_summary={"score": score, "asked": asked}, status="success"))
        db.commit()
        session["recent_questions"] = (recent_questions + [q])[-5:]
        _save_tutor_session(int(user_id), session)
        ans = (
            f"✅ **Chấm bài Practice**\n- Kết quả câu này: **{int(grade.get('score', 0))}/1**\n"
            f"- Nhận xét: {grade.get('feedback') or 'Ổn.'}\n"
            f"- Giải thích: {grade.get('explanation') or ''}\n\n"
            f"📊 Mini-session hiện tại: **{score}/{asked}**.\n"
            f"Bạn có thể yêu cầu: *'Hãy đặt câu hỏi để kiểm tra tôi về topic {p_topic}'* để làm câu tiếp theo."
        )
        return TutorChatData(
            answer_md=ans,
            was_answered=True,
            is_off_topic=False,
            refusal_message=None,
            suggested_topics=[p_topic],
            follow_up_questions=_normalize_follow_up_questions(p_topic, []),
            quick_check_mcq=[],
            sources=[],
            sources_used=[],
            confidence=0.85,
            retrieval={"mode": "practice_grade", "score": score, "asked": asked},
        ).model_dump()

    scope = _topic_scope(topic)
    gate_result = _is_question_on_topic_llm(db, question=q, topic=topic, document_ids=doc_ids)
    suggested_questions = [str(x).strip() for x in (gate_result.get("suggested_questions") or []) if str(x).strip()][:3]
    if not bool(gate_result.get("is_on_topic", True)):
    filters = {"document_ids": doc_ids} if doc_ids else {}
    query = f"{topic.strip()}: {q}" if topic and topic.strip() else q
    rag = corrective_retrieve_and_log(db=db, query=query, top_k=int(max(3, min(20, top_k))), filters=filters, topic=topic)

    off_topic_check = _off_topic_detector.check(question=q, topic=topic or "", rag_results=rag)
    if llm_gate_failed and off_topic_check["is_off_topic"]:
        topic_label = topic or "chủ đề học hiện tại"
        refusal = (
            f"Mình xin phép chưa trả lời vì câu hỏi có vẻ ngoài phạm vi chủ đề hiện tại ({scope}). "
            "Bạn thử một trong các câu gợi ý bên dưới nhé."
        )
        reason = str(gate_result.get("reason") or "off_topic")
        _log_tutor_flagged_question(
            db,
            user_id=int(user_id),
            question=q,
            topic=topic,
            reason=reason,
            suggested_topics=intent_suggestions,
        )
        return TutorChatData(
            answer_md=refusal,
            was_answered=False,
            is_off_topic=True,
            refusal_message=refusal,
            refusal_reason=reason,
            off_topic_reason=reason,
            suggested_topics=intent_suggestions,
            suggested_questions=suggested_questions,
            follow_up_questions=suggested_questions,
            quick_check_mcq=[],
            sources=[],
            sources_used=[],
            retrieval={"topic_gate": gate_result},
            retrieval={**(rag.get("corrective") or {}), "off_topic_check": off_topic_check, "llm_topic_gate": {"fallback": "lexical"}},
        ).model_dump()

    filters = {"document_ids": doc_ids} if doc_ids else {}
    query = f"{topic.strip()}: {q}" if topic and topic.strip() else q
    rag = corrective_retrieve_and_log(db=db, query=query, top_k=int(max(3, min(20, top_k))), filters=filters, topic=topic)

    corr = rag.get("corrective") or {}
    attempts = corr.get("attempts") or []
    last_try = attempts[-1] if isinstance(attempts, list) and attempts else {}
    try:
        best_rel = float(last_try.get("best_relevance", 0.0) or 0.0)
    except Exception:
        best_rel = 0.0

    chunks = rag.get("chunks") or []
    relevance_threshold = float(settings.CRAG_MIN_RELEVANCE) * 0.55
    has_low_relevance = bool(chunks) and best_rel < relevance_threshold
    if (not chunks) or has_low_relevance:
        reason = "no_retrieved_chunks" if not chunks else f"low_relevance:{best_rel:.3f}"
        _log_tutor_flagged_question(db, user_id=int(user_id), question=q, topic=topic, reason=reason, suggested_topics=intent_suggestions)
        return TutorChatData(answer_md="Tôi không tìm thấy thông tin này trong tài liệu học. Vui lòng hỏi giáo viên.", was_answered=False, is_off_topic=False, refusal_message=None, refusal_reason=reason, off_topic_reason=reason, suggested_topics=intent_suggestions, follow_up_questions=_normalize_follow_up_questions(topic, []), quick_check_mcq=[], sources=[], sources_used=[], confidence=0.35, retrieval={**corr, "note": "POSTCHECK_OFF_TOPIC", "llm_topic_gate": llm_gate_result or {"fallback": "lexical"}}).model_dump()

    good, bad = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    bad_ratio = float(len(bad)) / float(max(1, len(chunks)))
    if (not good) or (bad_ratio >= float(settings.OCR_BAD_CHUNK_RATIO) and len(good) < 2):
        msg = (
            "Mình chưa thể trả lời chắc chắn vì phần tài liệu mình truy xuất được đang bị **lỗi OCR / rời rạc** (chữ bị vỡ, thiếu dấu, sai dòng).\n\n"
            "Bạn có thể upload lại file .docx/PDF có text layer, hoặc dán 10–30 dòng liên quan để mình giải thích tốt hơn."
        )
        return TutorChatData(answer_md=msg, was_answered=False, is_off_topic=False, refusal_message=None, refusal_reason="ocr_quality_too_low", off_topic_reason="ocr_quality_too_low", suggested_topics=intent_suggestions, follow_up_questions=_normalize_follow_up_questions(topic, []), quick_check_mcq=[], sources=[], sources_used=[], confidence=0.3, retrieval={**(rag.get("corrective") or {}), "note": "OCR_QUALITY_TOO_LOW"}).model_dump()
    chunks = good

    sources = []
    for c in chunks[: min(len(chunks), int(top_k))]:
        sources.append({"chunk_id": int(c.get("chunk_id")), "document_id": int(c.get("document_id")) if c.get("document_id") is not None else None, "document_title": c.get("document_title") or c.get("title"), "score": float(c.get("score", 0.0) or 0.0), "preview": _src_preview(c.get("text") or ""), "meta": c.get("meta") or {}})
    sources_used = _extract_sources_used(sources)
    evidence_previews = [str((s or {}).get("preview") or "").strip() for s in sources[:6] if str((s or {}).get("preview") or "").strip()]
    gate = _llm_offtopic_gate(question=q, topic=topic, evidence_previews=evidence_previews)
    if gate.get("status") == "out_of_scope":
        reason = str(gate.get("reason") or "llm_offtopic_out_of_scope")
        refusal_message = (
            f"Mình xin phép chưa trả lời câu này vì có vẻ nằm ngoài phạm vi tài liệu/chủ đề hiện tại ({scope}). "
            f"Bạn có thể hỏi lại theo hướng trong phạm vi, ví dụ: '{_build_redirect_hint(topic)}'."
        )
        _log_tutor_flagged_question(db, user_id=int(user_id), question=q, topic=topic, reason=reason, suggested_topics=intent_suggestions)
        return TutorChatData(
            answer_md=refusal_message,
            was_answered=False,
            is_off_topic=True,
            refusal_message=refusal_message,
            refusal_reason=reason,
            off_topic_reason=reason,
            suggested_topics=intent_suggestions,
            follow_up_questions=_suggest_on_topic_questions(topic, q),
            quick_check_mcq=[],
            sources=[],
            sources_used=[],
            confidence=float(gate.get("confidence", 0.0) or 0.0),
            retrieval={**(rag.get("corrective") or {}), "llm_offtopic_gate": gate, "llm_topic_gate": llm_gate_result or {"fallback": "lexical"}},
        ).model_dump()
    if gate.get("status") == "uncertain":
        ask_message = (
            f"Mình chưa chắc câu hỏi đang nhắm tới phần nào trong '{scope}'. "
            f"Bạn giúp mình làm rõ hơn (nêu bài/chương/khái niệm cụ thể) để mình trả lời chính xác nhé."
        )
        return TutorChatData(
            answer_md=ask_message,
            was_answered=False,
            is_off_topic=False,
            refusal_message=None,
            refusal_reason="llm_offtopic_uncertain",
            off_topic_reason="llm_offtopic_uncertain",
            suggested_topics=intent_suggestions,
            follow_up_questions=_normalize_follow_up_questions(topic, []),
            quick_check_mcq=[],
            sources=[],
            sources_used=[],
            confidence=float(gate.get("confidence", 0.0) or 0.0),
            retrieval={**(rag.get("corrective") or {}), "llm_offtopic_gate": gate},
        ).model_dump()

    quick_mcq = []
    try:
        quick_mcq = clean_mcq_questions(_generate_mcq_from_chunks(topic=topic or "tài liệu", level="beginner", question_count=2, chunks=chunks), limit=2)
    except Exception:
        quick_mcq = []

    prev_note = ""
    if recent_questions:
        prev = recent_questions[-1]
        if _tokenize_vi(prev) & _tokenize_vi(q):
            prev_note = f"Ở câu hỏi trước bạn hỏi về: '{prev}'. Câu này có liên quan nên mình nối tiếp phần cũ.\n\n"

    if llm_available():
        packed = pack_chunks(chunks, max_chunks=min(4, len(chunks)), max_chars_per_chunk=750, max_total_chars=2800)
        rag_context = "\n\n".join([f"[chunk_id:{c.get('chunk_id')}] {str(c.get('text') or '')}" for c in packed])
        sys = TUTOR_SYSTEM_PROMPT.format(topic_scope=scope, rag_context=rag_context, user_question_summary=(q[:90] + "…") if len(q) > 90 else q)
        user = {"question": q, "topic": (topic or "").strip() or None, "session_history": {"recent_questions": recent_questions[-5:], "explained_topics": explained_topics[-8:]}, "output_format": {"answer_md": "markdown", "follow_up_questions": ["string", "string", "string"]}}
        try:
            resp = chat_json(messages=[{"role": "system", "content": sys}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}], temperature=0.25, max_tokens=1200)
            if isinstance(resp, dict) and (resp.get("answer_md") or "").strip():
                answer_md = prev_note + str(resp.get("answer_md") or "").strip()
                fu = _normalize_follow_up_questions(topic, [str(x).strip() for x in (resp.get("follow_up_questions") or []) if str(x).strip()])
                answer_md = _append_topic_aware_section(answer_md, topic=topic, follow_ups=fu, homework_links=_related_homework_links(db, user_id=int(user_id), topic=topic))
                if topic:
                    explained_topics = (explained_topics + [topic])[-8:]
                session["recent_questions"] = (recent_questions + [q])[-5:]
                session["explained_topics"] = explained_topics
                _save_tutor_session(int(user_id), session)
                confidence = min(0.98, max(0.5, 0.6 + (best_rel * 0.4)))
                return TutorChatData(answer_md=answer_md, was_answered=True, is_off_topic=False, refusal_message=None, refusal_reason=None, off_topic_reason=None, suggested_topics=intent_suggestions, follow_up_questions=fu, quick_check_mcq=(quick_mcq[:2]), sources=sources, sources_used=sources_used, confidence=confidence, retrieval=rag.get("corrective") or {}).model_dump()
        except Exception:
            pass

    bullets = []
    for c in chunks[:3]:
        txt = " ".join(str(c.get("text") or "").split())
        if len(txt) > 260:
            txt = txt[:257].rstrip() + "…"
        if txt:
            bullets.append(f"- {txt}")
    answer_md = (
        ("Mình đang ở chế độ **không dùng LLM**. Các đoạn liên quan nhất:\n\n" + "\n".join(bullets))
        if bullets
        else "Mình **chưa đủ thông tin trong tài liệu** để trả lời chắc chắn câu này."
    )
    fu = _normalize_follow_up_questions(topic, [])
    answer_md = _append_topic_aware_section(prev_note + answer_md, topic=topic, follow_ups=fu, homework_links=_related_homework_links(db, user_id=int(user_id), topic=topic))
    if topic:
        explained_topics = (explained_topics + [topic])[-8:]
    session["recent_questions"] = (recent_questions + [q])[-5:]
    session["explained_topics"] = explained_topics
    _save_tutor_session(int(user_id), session)
    return TutorChatData(answer_md=answer_md, was_answered=bool(bullets), is_off_topic=False, refusal_message=None, refusal_reason=None if bullets else "insufficient_context", off_topic_reason=None if bullets else "insufficient_context", suggested_topics=intent_suggestions, follow_up_questions=fu, quick_check_mcq=quick_mcq, sources=sources, sources_used=sources_used, confidence=0.55 if bullets else 0.4, retrieval=rag.get("corrective") or {}).model_dump()


def tutor_generate_questions(
    db: Session,
    *,
    user_id: int,
    topic: str,
    level: str | None = None,
    question_count: int = 6,
    top_k: int = 8,
    document_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Generate a *fresh* set of practice questions from the teacher's documents.

    Design goal (per user requirement): questions are NOT based on a fixed framework.
    The system should discover what is in the document for the chosen topic and ask
    suitable questions (definitions / steps / formulas / examples / pitfalls / comparisons...).
    """

    ensure_user_exists(db, int(user_id), role="student")

    t = (topic or "").strip()
    if not t:
        raise HTTPException(status_code=422, detail="Missing topic")

    qc = int(question_count or 0)
    qc = max(1, min(20, qc))

    # Auto-scope to teacher docs by default
    doc_ids = list(document_ids or [])
    if not doc_ids:
        auto = auto_document_ids_for_query(db, t, preferred_user_id=settings.DEFAULT_TEACHER_ID, max_docs=3)
        if auto:
            doc_ids = auto

    filters = {"document_ids": doc_ids} if doc_ids else {}

    # Retrieval query: keep it simple (topic only) to avoid imposing a template.
    rag = corrective_retrieve_and_log(
        db=db,
        query=t,
        top_k=int(max(6, min(30, top_k))),
        filters=filters,
        topic=t,
    )

    chunks = rag.get("chunks") or []
    good, bad = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    bad_ratio = float(len(bad)) / float(max(1, len(chunks)))
    if (not good) or (bad_ratio >= float(settings.OCR_BAD_CHUNK_RATIO) and len(good) < 2):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NEED_CLEAN_TEXT",
                "message": "CONTEXT bị lỗi OCR / rời rạc nên không thể sinh câu hỏi chắc chắn.",
                "reason": f"bad_chunk_ratio={bad_ratio:.2f}, good={len(good)}, total={len(chunks)}",
                "suggestion": "Hãy upload file .docx hoặc PDF có text layer / hoặc copy-paste đúng mục cần luyện.",
                "debug": {"sample_bad": bad[:2]},
            },
        )
    chunks = good

    # Build sources for UI/debug
    sources = []
    for c in chunks[: min(len(chunks), int(top_k))]:
        sources.append(
            {
                "chunk_id": int(c.get("chunk_id")),
                "document_id": int(c.get("document_id")) if c.get("document_id") is not None else None,
                "document_title": c.get("document_title") or c.get("title"),
                "score": float(c.get("score", 0.0) or 0.0),
                "preview": _src_preview(c.get("text") or ""),
                "meta": c.get("meta") or {},
            }
        )

    packed = pack_chunks(chunks, max_chunks=min(8, len(chunks)), max_chars_per_chunk=900, max_total_chars=5200)
    valid_ids = [int(c["chunk_id"]) for c in packed] if packed else []

    # Build a compact "topic profile" so the LLM can ask questions based on what's actually in the text.
    body_for_profile = "\n\n".join([str(c.get("text") or "") for c in packed]) if packed else ""
    topic_profile = build_topic_details(body_for_profile, title=t) if body_for_profile.strip() else {
        "title": t,
        "outline": [],
        "key_points": [],
        "definitions": [],
        "examples": [],
        "formulas": [],
        "faq": [],
        "misconceptions": [],
        "exercises": [],
    }

    def _tok(s: str) -> set[str]:
        s = (s or "").lower()
        return {w for w in __import__("re").findall(r"[\wÀ-ỹ]+", s) if len(w) >= 3}

    def _best_sources(text_hint: str, k: int = 2) -> List[Dict[str, int]]:
        if not packed:
            return []
        hint = _tok(text_hint)
        scored = []
        for c in packed:
            cid = int(c.get("chunk_id"))
            ct = _tok(f"{c.get('title') or ''} {c.get('text') or ''}")
            scored.append((len(hint & ct), cid))
        scored.sort(reverse=True)
        picked = [cid for score, cid in scored if score > 0][:k]
        if not picked:
            picked = [int(packed[0]["chunk_id"])]
        return [{"chunk_id": int(x)} for x in picked]

    # LLM path: generate varied questions WITHOUT a fixed framework.
    if llm_available() and packed:
        sys = (
            "Bạn là trợ giảng. Nhiệm vụ: sinh bộ CÂU HỎI LUYỆN TẬP dựa CHỈ trên evidence_chunks. "
            "Quan trọng: KHÔNG dùng một 'khung sẵn' (ví dụ: luôn hỏi định nghĩa → quy trình → ưu/nhược...). "
            "Hãy đọc topic_profile và tự chọn góc hỏi phù hợp với nội dung thật sự có trong văn bản. "
            "Nếu topic_profile cho thấy có quy trình/bước làm, hãy hỏi về bước/điều kiện; nếu có công thức, hỏi ý nghĩa và cách áp dụng; "
            "nếu có ví dụ/tình huống, hỏi phân tích; nếu có lỗi thường gặp/misconceptions, hỏi cách phát hiện/sửa. "
            "Không bịa kiến thức ngoài CONTEXT. Không copy nguyên văn dài."
        )

        user = {
            "topic": t,
            "level": (level or "").strip() or None,
            "question_count": qc,
            "topic_profile": topic_profile,
            "evidence_chunks": packed,
            "output_format": {
                "status": "OK|NEED_CLEAN_TEXT",
                "questions": [
                    {
                        "type": "open_ended",
                        "stem": "string",
                        "hints": ["string"],
                        "sources": [{"chunk_id": 123}],
                    }
                ],
            },
            "constraints": [
                "Mỗi câu hỏi phải bám ít nhất 1 chunk_id trong evidence_chunks (sources).",
                "Câu hỏi phải cụ thể, có yêu cầu rõ ràng, tránh mơ hồ.",
                "Không nhắc các từ: chunk, evidence, trích, theo tài liệu.",
                "Các câu phải đa dạng và PHÙ HỢP với nội dung, không lặp ý.",
            ],
        }

        try:
            resp = chat_json(
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
                temperature=0.35,
                max_tokens=1600,
            )
        except Exception:
            resp = None

        if isinstance(resp, dict) and str(resp.get("status", "")).upper() == "NEED_CLEAN_TEXT":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "NEED_CLEAN_TEXT",
                    "message": "CONTEXT không đủ rõ để sinh câu hỏi bám tài liệu.",
                    "reason": resp.get("reason") or resp.get("message") or "CONTEXT bị rời rạc/ký tự lỗi hoặc thiếu thông tin chắc chắn.",
                    "suggestion": resp.get("suggestion") or "Hãy upload file .docx hoặc PDF có text layer / hoặc copy text của mục cần luyện.",
                },
            )

        raw_qs = resp.get("questions") if isinstance(resp, dict) else None
        if isinstance(raw_qs, list) and raw_qs:
            cleaned = []
            seen = set()
            for q in raw_qs:
                if not isinstance(q, dict):
                    continue
                stem = " ".join(str(q.get("stem") or "").split()).strip()
                if len(stem) < 12:
                    continue
                key = stem.lower()
                if key in seen:
                    continue
                seen.add(key)

                hints = [" ".join(str(x).split()).strip() for x in (q.get("hints") or []) if str(x).strip()]
                sources_raw = q.get("sources")
                if isinstance(sources_raw, dict):
                    sources_raw = [sources_raw]
                s_ok: List[Dict[str, int]] = []
                if isinstance(sources_raw, list):
                    for it in sources_raw:
                        cid = it.get("chunk_id") if isinstance(it, dict) else it
                        try:
                            cid_i = int(cid)
                        except Exception:
                            continue
                        if cid_i in valid_ids:
                            s_ok.append({"chunk_id": cid_i})
                s_ok = s_ok[:2]
                if not s_ok:
                    s_ok = _best_sources(f"{t} {stem}", k=2)

                cleaned.append({"type": "open_ended", "stem": stem, "hints": hints[:3], "sources": s_ok})
                if len(cleaned) >= qc:
                    break

            if cleaned:
                return TutorGenerateQuestionsData(
                    topic=t,
                    level=(level or "").strip() or None,
                    questions=cleaned,
                    sources=sources,
                    retrieval=rag.get("corrective") or {},
                ).model_dump()

    # Offline fallback: build questions from the extracted topic_profile.
    questions: List[Dict[str, Any]] = []

    defs = topic_profile.get("definitions") or []
    kps = topic_profile.get("key_points") or []
    exs = topic_profile.get("examples") or []
    misc = topic_profile.get("misconceptions") or []

    def _add(stem: str):
        stem = " ".join((stem or "").split()).strip()
        if len(stem) < 12:
            return
        if any(stem.lower() == q["stem"].lower() for q in questions):
            return
        questions.append({"type": "open_ended", "stem": stem, "hints": [], "sources": _best_sources(stem, k=2)})

    # Pick a few different angles based on what exists in the text.
    if isinstance(defs, list) and defs:
        d0 = defs[0]
        term = (d0.get("term") if isinstance(d0, dict) else "") or t
        _add(f"Hãy giải thích '{term}' theo ý bạn và nêu một ví dụ minh hoạ.")

    if isinstance(kps, list) and kps:
        _add(f"Trong chủ đề '{t}', hãy tóm tắt 3 ý chính quan trọng nhất và giải thích vì sao chúng quan trọng.")

    if isinstance(misc, list) and misc:
        m0 = misc[0]
        _add(f"Nêu một hiểu lầm/sai lầm phổ biến liên quan đến '{t}' và cách tránh.")

    if isinstance(exs, list) and exs:
        _add(f"Hãy phân tích ví dụ trong tài liệu liên quan đến '{t}': mục tiêu, các bước/chọn lựa chính và kết quả.")

    # Fill remaining with general-but-not-fixed prompts.
    while len(questions) < qc:
        idx = len(questions) + 1
        _add(f"Câu {idx}: Hãy đặt một tình huống thực tế và mô tả cách bạn áp dụng '{t}' để giải quyết.")
        if len(questions) >= qc:
            break

    return TutorGenerateQuestionsData(
        topic=t,
        level=(level or "").strip() or None,
        questions=questions[:qc],
        sources=sources,
        retrieval=rag.get("corrective") or {},
    ).model_dump()
