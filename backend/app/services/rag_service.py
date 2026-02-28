from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.rag_query import RAGQuery
from app.services import vector_store
from app.services import rerank_service


_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Normalize whitespace + casing for simple lexical matching.

    NOTE: We purposely keep Vietnamese accents (đ, ư, ơ, ...) intact.
    """
    return _WS_RE.sub(" ", (text or "").strip().lower())


def _tokenize(text: str) -> List[str]:
    # \w matches unicode letters/digits/underscore in Python (incl. Vietnamese).
    return [t for t in re.findall(r"[\w]+", _normalize(text)) if t]


def _contains_word(token: str, text_norm: str) -> bool:
    """Whole-word match.

    Avoids substring matches like "quy" matching "quyền".
    """
    if not token:
        return False
    pattern = r"(?<!\w)" + re.escape(token) + r"(?!\w)"
    return re.search(pattern, text_norm) is not None


def _contains_phrase(phrase: str, text_norm: str) -> bool:
    """Whole-phrase match with loose boundaries."""
    phrase = _normalize(phrase)
    if not phrase:
        return False
    # treat any non-word character as boundary (spaces, punctuation, etc.)
    pattern = r"(^|[^\w])" + re.escape(phrase) + r"([^\w]|$)"
    return re.search(pattern, text_norm) is not None



def _clean_filter_list(values: Any) -> List[str]:
    """Normalize filter lists coming from Swagger/clients (avoid placeholder 'string')."""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    out: List[str] = []
    for v in list(values):
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        if s.lower() in {"string", "null", "none"}:
            continue
        out.append(s)
    return out


def _score(query: str, text: str) -> float:
    """Heuristic lexical scorer (better than substring hit-ratio).

    Goals:
    - Prefer exact phrase matches for multi-word queries (e.g. "đệ quy").
    - Match whole words only (avoid syllable/prefix false positives).
    - Still keep it dependency-free (no BM25, no embeddings).
    """
    q_norm = _normalize(query)
    t_norm = _normalize(text)

    q_tokens = _tokenize(q_norm)
    if not q_tokens:
        return 0.0

    # Single-word query: strict whole-word match
    if len(q_tokens) == 1:
        return 1.0 if _contains_word(q_tokens[0], t_norm) else 0.0

    # Multi-word query: phrase gets a strong boost
    phrase_hit = 1.0 if _contains_phrase(q_norm, t_norm) else 0.0

    # Also count whole-word token hits (use all tokens, but duplicates removed)
    uniq = list(dict.fromkeys(q_tokens))
    token_hits = sum(1 for tok in uniq if _contains_word(tok, t_norm))
    token_score = token_hits / max(1, len(uniq))

    # Blend: phrase dominates, tokens help when phrase isn't exact.
    if phrase_hit:
        return min(1.0, 0.75 * phrase_hit + 0.25 * token_score)
    return 0.9 * token_score



def auto_document_ids_for_query(
    db: Session,
    query: str,
    *,
    preferred_user_id: int | None = 1,
    max_docs: int = 2,
) -> List[int]:
    """Pick best-matching document_ids for a query when the caller didn't pass filters.

    This prevents cross-document leakage (e.g., Python MCQs appearing in a Deep Learning quiz)
    when multiple teacher documents exist in the DB.
    """
    q_raw = (query or "").strip()
    if not q_raw:
        return []

    # Loose normalization: treat punctuation (including hyphens) as spaces.
    q_norm = re.sub(r"[^\wÀ-ỹ]+", " ", q_raw.lower())
    q_norm = _WS_RE.sub(" ", q_norm).strip()
    q_tokens = [t for t in re.findall(r"[\wÀ-ỹ]+", q_norm) if len(t) >= 2]
    if not q_tokens:
        return []

    uniq = list(dict.fromkeys(q_tokens))

    # Prefer teacher documents (default user_id=1 in this demo).
    base_q = db.query(Document)
    if preferred_user_id is not None:
        try:
            pref_id = int(preferred_user_id)
        except Exception:
            pref_id = None
        if pref_id is not None:
            has_pref = db.query(Document.id).filter(Document.user_id == pref_id).limit(1).first()
            if has_pref:
                base_q = base_q.filter(Document.user_id == pref_id)

    docs = base_q.order_by(Document.created_at.desc()).limit(30).all()
    if not docs:
        return []

    scored: List[Tuple[float, int]] = []
    for d in docs:
        hay = f"{d.title or ''} {(d.content or '')[:3000]}"
        hay_norm = re.sub(r"[^\wÀ-ỹ]+", " ", hay.lower())
        hay_norm = _WS_RE.sub(" ", hay_norm).strip()

        # token hits (whole-word)
        hits = sum(1 for t in set(uniq) if _contains_word(t, hay_norm))
        token_score = hits / max(1, len(set(uniq)))

        # phrase bonus when we have a reasonably long phrase
        phrase_bonus = 0.0
        if len(q_norm) >= 12 and q_norm in hay_norm:
            phrase_bonus = 0.45

        score = float(token_score) + float(phrase_bonus)
        if score > 0:
            scored.append((score, int(d.id)))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Keep only reasonably relevant docs to avoid random matches.
    picked: List[int] = []
    for sc, did in scored:
        if sc < 0.20 and picked:
            break
        if sc < 0.20 and not picked:
            # allow a single weak match if everything is weak
            picked.append(int(did))
            break
        picked.append(int(did))
        if len(picked) >= max(1, int(max_docs)):
            break

    return picked

def _should_prefilter_token(tok: str, query_tokens: List[str]) -> bool:
    """Tokens used in SQL prefilter.

    For multi-word Vietnamese queries, short syllables cause a lot of noise
    (e.g., "quy" matches "quyền"). We therefore:
    - Always allow full-phrase prefilter.
    - For token OR prefilter: keep longer tokens (>=4) or numeric tokens.
    - If the query is a single token, allow it even if short (e.g., "if").
    """
    if not tok:
        return False
    if len(query_tokens) == 1:
        return True
    return tok.isdigit() or len(tok) >= 4


def _keyword_retrieve(db: Session, query: str, top_k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Keyword-based retrieval (dependency-free).

    Returns a list of chunk dicts: {chunk_id, document_id, title, chunk_index, score, text, meta}
    """
    filters = filters or {}
    raw_doc_ids = filters.get("document_ids")
    raw_tags = filters.get("tags")

    doc_ids: List[int] = []
    for s_id in _clean_filter_list(raw_doc_ids):
        try:
            doc_ids.append(int(s_id))
        except Exception:
            continue

    tags = _clean_filter_list(raw_tags)

    # IMPORTANT (perf/memory): do NOT load full Document objects here.
    # Document.content can be very large (full extracted text). Loading it during retrieval
    # can spike memory and kill the backend container (exit code 137 on Docker Desktop).
    # We only need doc.title for display, so select minimal columns.
    q = (
        db.query(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
            DocumentChunk.text,
            DocumentChunk.meta,
            Document.title,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
    )
    if doc_ids:
        q = q.filter(DocumentChunk.document_id.in_(doc_ids))
    if tags:
        q = q.filter(Document.tags.overlap(tags))

    # Light SQL prefilter, then score in Python.
    q_norm = _normalize(query)
    q_tokens = list(dict.fromkeys(_tokenize(q_norm)))
    ors = []
    if q_tokens:
        if len(q_tokens) >= 2 and q_norm:
            ors.append(DocumentChunk.text.ilike(f"%{q_norm}%"))
        for tok in q_tokens[:12]:
            if _should_prefilter_token(tok, q_tokens):
                ors.append(DocumentChunk.text.ilike(f"%{tok}%"))
    if ors:
        q = q.filter(or_(*ors))

    # Cap candidates to keep scoring bounded.
    # (The SQL prefilter is already loose; scoring on too many rows is wasteful.)
    MAX_CANDIDATES = 1200
    candidates = q.limit(MAX_CANDIDATES).all()

    scored: List[Tuple[float, tuple]] = []
    for ch_id, doc_id, chunk_index, text, meta, title in candidates:
        s = _score(query, text)
        if s <= 0:
            continue
        scored.append((float(s), (ch_id, doc_id, chunk_index, text, meta, title)))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Drop low-quality tail results.
    if scored:
        best = float(scored[0][0])
        min_keep = max(0.15, best * 0.60)
        filtered = [it for it in scored if float(it[0]) >= min_keep]
        scored = (filtered or scored)[: max(1, int(top_k))]
    else:
        scored = []

    chunks_out: List[Dict[str, Any]] = []
    for sc, row in scored:
        ch_id, doc_id, chunk_index, text, meta, title = row
        chunks_out.append(
            {
                "chunk_id": int(ch_id),
                "document_id": int(doc_id),
                "title": title,
                "chunk_index": int(chunk_index),
                "score": round(float(sc), 6),
                "text": text,
                "meta": meta or {},
            }
        )

    return chunks_out


def _semantic_retrieve(db: Session, query: str, top_k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Semantic retrieval using FAISS + embeddings (if enabled & ready)."""
    filters = filters or {}
    if not vector_store.is_enabled():
        return []
    try:
        return vector_store.search(db=db, query=query, top_k=top_k, filters=filters)
    except Exception:
        return []


def _rrf_fuse(
    semantic: List[Dict[str, Any]],
    keyword: List[Dict[str, Any]],
    top_k: int,
    k: int = 60,
    w_sem: float = 1.0,
    w_kw: float = 0.85,
) -> List[Dict[str, Any]]:
    """Fuse two ranked lists using Reciprocal Rank Fusion.

    We keep the chunk dict from semantic list when available (it usually contains better similarity scores),
    but we expose extra debug fields to help demos.
    """
    by_id: Dict[int, Dict[str, Any]] = {}
    scores: Dict[int, float] = {}

    def add(list_items: List[Dict[str, Any]], weight: float, src: str):
        for rank, item in enumerate(list_items, start=1):
            cid = item.get("chunk_id")
            if cid is None:
                continue
            try:
                cid_int = int(cid)
            except Exception:
                continue
            # store best item representation
            if cid_int not in by_id:
                by_id[cid_int] = dict(item)
            else:
                # prefer semantic fields (title/text/meta) but keep existing if missing
                for key in ["title", "text", "meta", "document_id", "chunk_index"]:
                    if not by_id[cid_int].get(key) and item.get(key) is not None:
                        by_id[cid_int][key] = item.get(key)
            # rrf
            scores[cid_int] = float(scores.get(cid_int, 0.0)) + float(weight) * (1.0 / float(k + rank))
            # debug
            by_id[cid_int].setdefault("_sources", set())
            by_id[cid_int]["_sources"].add(src)
            if src == "semantic":
                by_id[cid_int]["_score_semantic"] = item.get("score")
            elif src == "keyword":
                by_id[cid_int]["_score_keyword"] = item.get("score")

    add(semantic, w_sem, "semantic")
    add(keyword, w_kw, "keyword")

    fused = []
    for cid, item in by_id.items():
        item = dict(item)
        item["score"] = round(float(scores.get(cid, 0.0)), 8)
        # coerce debug set -> list
        srcs = item.pop("_sources", set())
        item["sources_mode"] = sorted(list(srcs))
        fused.append(item)

    fused.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return fused[: max(1, int(top_k))]


def retrieve_and_log(db: Session, query: str, top_k: int = 5, filters: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Retrieve relevant chunks and log the query.

    Modes:
    - hybrid: semantic + keyword fused by RRF (preferred when semantic is available)
    - semantic: semantic only
    - keyword: keyword-only fallback
    """
    filters = filters or {}

    base_k = max(1, int(top_k))

    # Fetch more candidates than we finally return (so reranking has room to improve precision).
    cand_mult = int(getattr(settings, "RERANK_CANDIDATE_MULTIPLIER", 6) or 6)
    cand_mult = max(2, min(12, cand_mult))
    cand_k = max(base_k * cand_mult, 24)
    cand_k = min(120, cand_k)  # hard cap to keep latency stable

    # Always compute keyword candidates (cheap + robust in Vietnamese).
    kw = _keyword_retrieve(db=db, query=query, top_k=cand_k, filters=filters)

    # Semantic candidates (optional)
    sem = _semantic_retrieve(db=db, query=query, top_k=cand_k, filters=filters)

    if sem and kw:
        candidates = _rrf_fuse(semantic=sem, keyword=kw, top_k=cand_k)
        mode = "hybrid"
    elif sem:
        candidates = sem[: max(1, int(cand_k))]
        mode = "semantic"
    else:
        candidates = kw[: max(1, int(cand_k))]
        mode = "keyword"

    # 2nd-stage reranking (LLM-as-a-Judge) to improve context quality
    max_cand = int(getattr(settings, "RERANK_MAX_CANDIDATES", 24) or 24)
    rerank_debug = {"enabled": False}
    chunks = candidates[:base_k]
    if (
        rerank_service.rerank_enabled()
        and base_k <= max_cand
        and len(candidates) > base_k
    ):
        cand_for_rerank = candidates[: max(base_k, min(len(candidates), max_cand))]
        try:
            chunks, rerank_debug = rerank_service.rerank(query=query, chunks=cand_for_rerank, top_k=base_k)
        except Exception:
            # Safety: never fail retrieval because reranking failed
            chunks = candidates[:base_k]
            rerank_debug = {"enabled": True, "method": "llm_judge", "error": "rerank_failed"}

    chunk_ids = [int(c["chunk_id"]) for c in (chunks or []) if c.get("chunk_id") is not None]

    rag_q = RAGQuery(query=query, top_k=top_k, filters=filters, result_chunk_ids=chunk_ids)
    db.add(rag_q)
    db.commit()
    db.refresh(rag_q)

    return {
        "mode": mode,
        "query_id": rag_q.id,
        "query": query,
        "top_k": int(top_k),
        "chunks": chunks,
        "debug": {
            "semantic_enabled": bool(vector_store.is_enabled()),
            "semantic_used": bool(sem),
            "keyword_used": bool(kw),
            "semantic_candidates": int(len(sem or [])),
            "keyword_candidates": int(len(kw or [])),
            "candidate_k": int(cand_k),
            "rerank": rerank_debug,
        },
    }
