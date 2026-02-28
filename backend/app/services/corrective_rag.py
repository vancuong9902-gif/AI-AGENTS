from __future__ import annotations

import re
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.rag_service import retrieve_and_log
from app.services.llm_service import llm_available, chat_json


_WORD_RX = re.compile(r"[A-Za-zÀ-ỹà-ỹ0-9]+", flags=re.UNICODE)

_VI_STOP = {
    "và",
    "hoặc",
    "là",
    "của",
    "cho",
    "trong",
    "với",
    "các",
    "một",
    "những",
    "này",
    "đó",
    "theo",
    "dựa",
    "trên",
    "tài",
    "liệu",
    "bài",
    "học",
}


def _tokens(text: str) -> List[str]:
    toks = [t.lower() for t in _WORD_RX.findall(text or "")]
    out = []
    for t in toks:
        if len(t) < 3:
            continue
        if t in _VI_STOP:
            continue
        out.append(t)
    # de-dup (preserve order)
    seen = set()
    uniq = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    return uniq[:18]


def _chunk_relevance(query_tokens: List[str], chunk_text: str) -> float:
    if not query_tokens:
        return 0.0
    t = (chunk_text or "").lower()
    hits = 0
    for tok in query_tokens:
        if tok in t:
            hits += 1
    return float(hits) / float(len(query_tokens))


def _grade_retrieval(query: str, chunks: List[Dict[str, Any]]) -> Tuple[float, float, List[float]]:
    qt = _tokens(query)
    scores = [_chunk_relevance(qt, str(c.get("text") or "")) for c in (chunks or [])]
    if not scores:
        return 0.0, 0.0, []
    best = max(scores)
    top = sorted(scores, reverse=True)[: min(3, len(scores))]
    avg_top = float(mean(top)) if top else 0.0
    return float(best), float(avg_top), scores


def _needs_correction(query: str, chunks: List[Dict[str, Any]], min_rel: float) -> bool:
    qt = _tokens(query)
    if len(qt) < 2:
        # query too short; lexical grading isn't reliable
        return False
    best, avg_top, _ = _grade_retrieval(query, chunks)
    # If even the best chunk barely matches the query, try rewriting.
    return (best < float(min_rel)) and (avg_top < float(min_rel) * 0.85)


def _rewrite_query_heuristic(query: str, topic: Optional[str] = None) -> str:
    base = (query or "").strip()
    # remove common filler phrases
    base = re.sub(r"\b(theo|dựa|trên|tài\s*liệu|trích|đoạn|chunk)\b", " ", base, flags=re.IGNORECASE)
    base = " ".join(base.split())
    toks = _tokens(base)
    core = " ".join(toks[:10]) if toks else base
    if topic and topic.strip():
        # add topic to anchor
        return f"{topic.strip()} {core} khái niệm ví dụ lỗi thường gặp".strip()
    return f"{core} khái niệm ví dụ lỗi thường gặp".strip()


def _rewrite_query_with_llm(query: str, topic: Optional[str] = None, doc_titles: Optional[List[str]] = None) -> Optional[str]:
    if not llm_available():
        return None
    sys = (
        "Bạn là Retrieval Query Rewriter cho hệ thống RAG. "
        "Mục tiêu: viết lại query ngắn gọn, nhiều từ khoá trọng tâm, tránh từ chung chung. "
        "Không thêm thông tin mới không có trong tài liệu; chỉ tối ưu truy vấn tìm kiếm." 
    )
    user = {
        "original_query": (query or "").strip(),
        "topic": (topic or "").strip() or None,
        "doc_titles": doc_titles or [],
        "constraints": [
            "Giữ cùng ngôn ngữ (ưu tiên tiếng Việt nếu query tiếng Việt).",
            "Ưu tiên cụm từ kỹ thuật/chủ đề thay vì câu dài.",
            "Không nhắc tới 'chunk', 'evidence', 'tài liệu' trong query.",
        ],
        "output_format": {"rewritten_query": "string"},
    }
    try:
        resp = chat_json(
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": __import__("json").dumps(user, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=180,
        )
        if isinstance(resp, dict):
            rq = (resp.get("rewritten_query") or "").strip()
            if rq and len(rq) >= 6:
                return rq
    except Exception:
        return None
    return None


def corrective_retrieve_and_log(
    db: Session,
    query: str,
    top_k: int = 6,
    filters: Optional[Dict[str, Any]] = None,
    *,
    topic: Optional[str] = None,
    doc_titles: Optional[List[str]] = None,
    max_iters: Optional[int] = None,
    min_relevance: Optional[float] = None,
) -> Dict[str, Any]:
    """Corrective RAG loop: retrieve -> grade -> (rewrite query -> retrieve)...

    Returns the final retrieve_and_log() payload plus a `corrective` field containing debug info.

    This follows the general CRAG idea: detect retrieval failure, rewrite query, and retry.
    """
    q = (query or "").strip()
    if not q:
        return retrieve_and_log(db=db, query=query, top_k=top_k, filters=filters or {})

    iters = int(max_iters if max_iters is not None else settings.CRAG_MAX_ITERS)
    iters = max(1, min(5, iters))
    thr = float(min_relevance if min_relevance is not None else settings.CRAG_MIN_RELEVANCE)

    debug: List[Dict[str, Any]] = []
    last = None

    for i in range(iters):
        data = retrieve_and_log(db=db, query=q, top_k=top_k, filters=filters or {})
        last = data
        chunks = data.get("chunks") or []
        best, avg_top, scores = _grade_retrieval(q, chunks)

        entry = {
            "iter": i + 1,
            "query": q,
            "mode": data.get("mode"),
            "best_relevance": round(float(best), 4),
            "avg_top_relevance": round(float(avg_top), 4),
        }

        if not chunks:
            entry["action"] = "no_chunks"
            debug.append(entry)
            break

        if not _needs_correction(q, chunks, thr):
            entry["action"] = "accept"
            debug.append(entry)
            break

        # rewrite & retry
        rq = _rewrite_query_with_llm(q, topic=topic, doc_titles=doc_titles) or _rewrite_query_heuristic(q, topic=topic)
        entry["action"] = "rewrite"
        entry["rewritten_query"] = rq
        debug.append(entry)

        # avoid loops
        if rq.strip().lower() == q.strip().lower():
            break
        q = rq

    if isinstance(last, dict):
        last["corrective"] = {
            "enabled": True,
            "max_iters": iters,
            "min_relevance": thr,
            "attempts": debug,
        }
    return last or {"mode": "keyword", "query": query, "top_k": top_k, "chunks": [], "corrective": {"enabled": True, "attempts": debug}}
