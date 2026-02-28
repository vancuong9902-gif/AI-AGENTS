from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from app.core.config import settings
from app.services.llm_service import llm_available, chat_json


def _mode() -> str:
    m = (getattr(settings, "RERANK_MODE", "auto") or "auto").strip().lower()
    if m in {"0", "false", "off", "none", "disable", "disabled"}:
        return "off"
    if m in {"auto", "llm_judge"}:
        return m
    # default safe
    return "auto"


def rerank_enabled() -> bool:
    m = _mode()
    if m == "off":
        return False
    # auto => only when llm is available
    if m == "auto":
        return bool(llm_available())
    return True


def _truncate(text: str, n: int) -> str:
    s = " ".join((text or "").split())
    if n and len(s) > int(n):
        return s[: int(n) - 1].rstrip() + "…"
    return s


def llm_judge_rerank(
    *,
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int,
    max_chars_per_chunk: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """LLM-as-a-Judge reranking.

    Returns: (reranked_chunks, debug)

    Notes:
    - Only uses chunk excerpts (truncated) to keep cost/latency stable.
    - Adds `rerank_score` and `rerank_reason` (short) into each chunk (best-effort).
    """

    if not llm_available() or not chunks:
        return chunks, {"enabled": False, "method": "llm_judge", "reason": "llm_unavailable_or_empty"}

    # Prepare payload
    packed = []
    for c in chunks:
        try:
            cid = int(c.get("chunk_id"))
        except Exception:
            continue
        packed.append(
            {
                "chunk_id": cid,
                "title": (c.get("document_title") or c.get("title") or "").strip() or None,
                "text": _truncate(str(c.get("text") or ""), max_chars_per_chunk),
            }
        )

    if not packed:
        return chunks, {"enabled": False, "method": "llm_judge", "reason": "no_valid_chunk_ids"}

    sys = (
        "Bạn là RERANKING JUDGE cho hệ thống RAG. "
        "Nhiệm vụ: chấm mức độ LIÊN QUAN của mỗi đoạn (chunk) so với QUERY, rồi sắp xếp lại. "
        "Chỉ dựa vào nội dung chunk được cung cấp. Không bịa. "
        "Điểm relevance từ 0..10 (10 = liên quan trực tiếp, trả lời đúng trọng tâm; 0 = không liên quan). "
        "Nếu chunk chỉ 'na ná' về từ khoá nhưng không đúng ngữ cảnh, phải cho điểm thấp. "
        "Trả về JSON đúng định dạng." 
    )
    user = {
        "query": (query or "").strip(),
        "top_k": int(max(1, top_k)),
        "chunks": packed,
        "output_format": {
            "ranked": [
                {
                    "chunk_id": 123,
                    "score": 0,
                    "reason": "string (<= 20 words)"
                }
            ],
            "top_chunk_ids": [123, 456],
        },
    }

    debug: Dict[str, Any] = {
        "enabled": True,
        "method": "llm_judge",
        "candidate_count": len(packed),
        "top_k": int(max(1, top_k)),
    }

    try:
        resp = chat_json(
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=900,
        )
    except Exception as e:
        debug["error"] = f"llm_call_failed: {type(e).__name__}"
        return chunks, debug

    ranked = resp.get("ranked") if isinstance(resp, dict) else None
    if not isinstance(ranked, list) or not ranked:
        debug["error"] = "invalid_llm_response"
        return chunks, debug

    score_by_id: Dict[int, float] = {}
    reason_by_id: Dict[int, str] = {}
    for item in ranked:
        if not isinstance(item, dict):
            continue
        cid = item.get("chunk_id")
        try:
            cid = int(cid)
        except Exception:
            continue
        try:
            sc = float(item.get("score", 0.0))
        except Exception:
            sc = 0.0
        sc = max(0.0, min(10.0, sc))
        score_by_id[cid] = sc
        rs = str(item.get("reason") or "").strip()
        if rs:
            reason_by_id[cid] = rs

    # Apply scores to chunks, keep stable ordering for ties/missing.
    enriched: List[Dict[str, Any]] = []
    for idx, c in enumerate(chunks):
        c2 = dict(c)
        try:
            cid = int(c2.get("chunk_id"))
        except Exception:
            cid = None
        if cid is not None and cid in score_by_id:
            c2["_score_pre_rerank"] = c2.get("score")
            c2["rerank_score"] = float(score_by_id[cid])
            if cid in reason_by_id:
                c2["rerank_reason"] = reason_by_id[cid]
        else:
            c2["rerank_score"] = -1.0
        c2["_rerank_idx"] = idx
        enriched.append(c2)

    # Sort by: rerank_score (desc) -> original retrieval score (desc) -> stable order (asc)
    enriched.sort(
        key=lambda x: (
            float(x.get("rerank_score", -1.0)),
            float(x.get("score", 0.0) or 0.0),
            -int(x.get("_rerank_idx", 0)),
        ),
        reverse=True,
    )
    # Drop helper key
    for c in enriched:
        c.pop("_rerank_idx", None)

    kept = enriched[: max(1, int(top_k))]
    debug["used"] = True
    debug["reranked_ids"] = [int(c.get("chunk_id")) for c in kept if c.get("chunk_id") is not None]
    # Store top few reasons for debugging
    top_reasons = []
    for c in kept[:5]:
        try:
            cid = int(c.get("chunk_id"))
        except Exception:
            continue
        if cid in score_by_id:
            top_reasons.append({"chunk_id": cid, "score": score_by_id[cid], "reason": reason_by_id.get(cid, "")})
    debug["top_reasons"] = top_reasons
    return kept, debug


def rerank(
    *,
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Main entry.

    Currently supports LLM-as-a-Judge reranking (technique #5) because it works
    with any OpenAI-compatible LLM and requires no extra infrastructure.
    """
    if not rerank_enabled():
        return chunks[: max(1, int(top_k))], {"enabled": False, "method": _mode(), "reason": "disabled"}

    max_chars = int(getattr(settings, "RERANK_MAX_CHARS_PER_CHUNK", 850) or 850)
    return llm_judge_rerank(query=query, chunks=chunks, top_k=top_k, max_chars_per_chunk=max_chars)
