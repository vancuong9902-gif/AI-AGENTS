from __future__ import annotations

import json
import hashlib
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.embedding_service import embed_text, embed_texts

try:
    import faiss  # type: ignore
    import numpy as np  # type: ignore

    FAISS_AVAILABLE = True
except Exception:
    faiss = None  # type: ignore
    np = None  # type: ignore
    FAISS_AVAILABLE = False


# Use the configured embeddings model (supports OpenAI, Azure, Ollama, gateways).
# Note: dimension is inferred at runtime from the embedding response.

def _embed_model() -> str:
    m = (getattr(settings, 'OPENAI_EMBEDDING_MODEL', None) or getattr(settings, 'OPENAI_EMBED_MODEL', None) or 'text-embedding-3-small')
    return str(m).strip() or 'text-embedding-3-small'

# Current embedding dimension (inferred).
_EMBED_DIM: int | None = None

# backend/app/services -> parents[2] == backend/
BASE_DIR = Path(__file__).resolve().parents[2]
VECTOR_DIR = BASE_DIR / "vector_db"
INDEX_PATH = VECTOR_DIR / "index.faiss"
META_PATH = VECTOR_DIR / "metadata.json"

_lock = threading.Lock()
_index = None
_meta: List[Dict[str, Any]] = []
_ready = False


def is_enabled() -> bool:
    """Semantic RAG is enabled only when:
    - FAISS is installed
    - OPENAI_API_KEY is set (embeddings provider)
    - SEMANTIC_RAG_ENABLED is True

    NOTE: Khi dùng LLM local (Ollama) chỉ để sinh quiz/lesson, hãy để OPENAI_API_KEY trống
    hoặc set SEMANTIC_RAG_ENABLED=false để tránh gọi embeddings.
    """
    return bool(
        FAISS_AVAILABLE
        and settings.SEMANTIC_RAG_ENABLED
        and (settings.OPENAI_API_KEY or getattr(settings, "AZURE_OPENAI_API_KEY", None))
    )



def _normalize(mat):
    """Row-normalize vectors for cosine similarity (IndexFlatIP)."""
    if np is None:
        return mat
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def _hash_text(text: str) -> str:
    """Stable hash for dedup/incremental indexing.

    We normalize whitespace to avoid hash changes from extraction quirks.
    """
    t = " ".join(str(text or "").split())
    return hashlib.sha1(t.encode("utf-8", errors="ignore")).hexdigest()



def _ensure_dirs() -> None:
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)


def load_if_exists() -> None:
    """Load FAISS + metadata from disk (safe to call multiple times)."""
    global _index, _meta, _ready, _EMBED_DIM

    if not FAISS_AVAILABLE:
        _index = None
        _meta = []
        _ready = False
        _EMBED_DIM = None
        return

    _ensure_dirs()

    if INDEX_PATH.exists() and META_PATH.exists():
        try:
            _index = faiss.read_index(str(INDEX_PATH))
            d = int(getattr(_index, 'd', 0) or 0)
            _EMBED_DIM = d or None
            _meta = json.loads(META_PATH.read_text(encoding='utf-8'))
            _ready = bool(_meta) and int(getattr(_index, 'ntotal', 0)) == len(_meta)
            return
        except Exception:
            # corrupted files -> reset
            pass

    # Placeholder empty index; dimension will be corrected on first add/rebuild.
    dim = int(_EMBED_DIM or 1536)
    _index = faiss.IndexFlatIP(dim)
    _EMBED_DIM = int(getattr(_index, 'd', dim))
    _meta = []
    _ready = False



def _persist() -> None:
    if not FAISS_AVAILABLE or _index is None:
        return
    _ensure_dirs()
    faiss.write_index(_index, str(INDEX_PATH))
    META_PATH.write_text(json.dumps(_meta, ensure_ascii=False, indent=2), encoding="utf-8")


def status() -> Dict[str, Any]:
    return {
        "faiss_available": bool(FAISS_AVAILABLE),
        "openai_key_set": bool(settings.OPENAI_API_KEY),
        "azure_key_set": bool(getattr(settings, "AZURE_OPENAI_API_KEY", None)),
        "semantic_rag_enabled": bool(is_enabled()),
        "vector_ready": bool(_ready),
        "vector_total": int(len(_meta)),
    }


def add_chunks(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Embed + add chunks to FAISS.

    chunks item required keys: chunk_id, document_id, text

    Improvements:
    - Skip chunks already indexed (by chunk_id) to avoid duplicate vectors.
    - Persist a stable text hash in metadata for debugging / future maintenance.
    """
    global _ready, _index, _meta

    if not is_enabled():
        raise RuntimeError("Semantic RAG not enabled (need faiss-cpu + OPENAI_API_KEY).")

    if not chunks:
        return {"added": 0, "skipped": 0, "total": len(_meta)}

    # Ensure index is loaded.
    with _lock:
        if _index is None:
            load_if_exists()
        assert _index is not None
        existing_ids = {int(m.get("chunk_id")) for m in (_meta or []) if m.get("chunk_id") is not None}

    # Dedup by chunk_id (across index + within this call)
    to_add: List[Dict[str, Any]] = []
    seen_in_call = set()
    for c in chunks:
        try:
            cid = int(c["chunk_id"])
        except Exception:
            continue
        if cid in existing_ids or cid in seen_in_call:
            continue
        seen_in_call.add(cid)
        to_add.append(c)

    if not to_add:
        return {"added": 0, "skipped": len(chunks), "total": len(_meta)}

    texts = [str(c.get("text") or "") for c in to_add]
    vecs = embed_texts(texts, model=_embed_model())

    if np is None:
        raise RuntimeError("numpy is required for semantic RAG")

    mat = np.array(vecs, dtype="float32")
    mat = _normalize(mat)

    # Ensure index dimension matches the embedding output.
    dim = int(mat.shape[1])

    with _lock:
        global _EMBED_DIM
        if _index is None:
            load_if_exists()
        assert _index is not None
        if int(getattr(_index, 'd', dim)) != dim:
            # Model/dimension changed (e.g., switching from OpenAI 1536-dim to Ollama 768-dim).
            # Reset index + metadata; caller may optionally call /api/rag/rebuild for full rebuild.
            _index = faiss.IndexFlatIP(dim)
            _meta = []
            _ready = False
            _EMBED_DIM = dim
            _persist()
        else:
            _EMBED_DIM = int(getattr(_index, 'd', dim))

    # Add under lock and re-check duplicates (in case concurrent add happened)
    added = 0
    skipped = len(chunks) - len(to_add)

    with _lock:
        assert _index is not None
        existing_ids = {int(m.get("chunk_id")) for m in (_meta or []) if m.get("chunk_id") is not None}
        final_add = []
        final_mat_rows = []
        for row, c in zip(mat, to_add):
            cid = int(c["chunk_id"])
            if cid in existing_ids:
                skipped += 1
                continue
            final_add.append(c)
            final_mat_rows.append(row)

        if final_add:
            mat2 = np.stack(final_mat_rows, axis=0).astype("float32")
            _index.add(mat2)
            for c in final_add:
                _meta.append(
                    {
                        "chunk_id": int(c["chunk_id"]),
                        "document_id": int(c["document_id"]),
                        "hash": _hash_text(c.get("text") or ""),
                    }
                )
            added = len(final_add)

        _ready = bool(_meta)
        _persist()

    return {"added": int(added), "skipped": int(skipped), "total": int(len(_meta))}


def rebuild_from_db(db: Session) -> Dict[str, Any]:
    """Rebuild the whole vector index from DocumentChunk table."""
    global _index, _meta, _ready, _EMBED_DIM

    if not is_enabled():
        raise RuntimeError("Semantic RAG not enabled (need faiss-cpu + OPENAI_API_KEY).")

    from app.models.document_chunk import DocumentChunk

    rows = db.query(DocumentChunk).order_by(DocumentChunk.id.asc()).all()
    items = [{"chunk_id": r.id, "document_id": r.document_id, "text": r.text} for r in rows]

    if np is None:
        raise RuntimeError("numpy is required for semantic RAG")

    texts = [i["text"] for i in items]
    if not texts:
        with _lock:
            # Keep a placeholder index so status() works; dimension will be set on first add/rebuild.
            _index = faiss.IndexFlatIP(int(_EMBED_DIM or 1536))
            _meta = []
            _ready = False
            _persist()
        return {"rebuilt": True, "added": 0, "total": 0}

    vecs = embed_texts(texts, model=_embed_model())
    mat = np.array(vecs, dtype="float32")
    mat = _normalize(mat)

    dim = int(mat.shape[1])

    with _lock:
        _EMBED_DIM = dim
        _index = faiss.IndexFlatIP(dim)
        _index.add(mat)
        _meta = [
            {"chunk_id": int(i["chunk_id"]), "document_id": int(i["document_id"]), "hash": _hash_text(i.get("text") or "")}
            for i in items
        ]
        _ready = True
        _persist()

    return {"rebuilt": True, "added": len(items), "total": len(items)}



def search(db: Session, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Vector search over indexed chunks.

    Returns chunk dicts compatible with old rag_service output.
    """
    if not is_enabled() or not _ready or _index is None:
        raise RuntimeError("Vector index not ready")

    if np is None:
        raise RuntimeError("numpy is required for semantic RAG")

    filters = filters or {}
    doc_ids = filters.get("document_ids") or []
    tags = filters.get("tags") or []

    # Over-fetch to allow filtering.
    fetch_n = max(int(top_k) * 10, 50)

    q_vec = np.array([embed_text(str(query), model=EMBED_MODEL)], dtype="float32")
    q_vec = _normalize(q_vec)

    with _lock:
        D, I = _index.search(q_vec, fetch_n)

    raw_hits: List[Dict[str, Any]] = []
    for score, idx in zip(D[0].tolist(), I[0].tolist()):
        if idx < 0 or idx >= len(_meta):
            continue
        m = _meta[idx]
        raw_hits.append({"score": float(score), "chunk_id": int(m["chunk_id"]), "document_id": int(m["document_id"])})

    if not raw_hits:
        return []

    # Apply filters (document_ids, tags) using DB.
    allowed_ids = None
    if doc_ids or tags:
        from app.models.document import Document
        from app.models.document_chunk import DocumentChunk

        chunk_ids = [h["chunk_id"] for h in raw_hits]
        q = db.query(DocumentChunk.id).join(Document, Document.id == DocumentChunk.document_id).filter(DocumentChunk.id.in_(chunk_ids))
        if doc_ids:
            q = q.filter(DocumentChunk.document_id.in_(doc_ids))
        if tags:
            q = q.filter(Document.tags.overlap(tags))
        allowed_ids = {r[0] for r in q.all()}

    hits = raw_hits
    if allowed_ids is not None:
        hits = [h for h in hits if h["chunk_id"] in allowed_ids]

    hits.sort(key=lambda x: x["score"], reverse=True)
    hits = hits[: max(1, int(top_k))]

    # Fetch chunk text + doc title for output.
    from app.models.document import Document
    from app.models.document_chunk import DocumentChunk

    chunk_ids = [h["chunk_id"] for h in hits]
    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(DocumentChunk.id.in_(chunk_ids))
        .all()
    )
    by_id = {ch.id: (ch, doc) for ch, doc in rows}

    out: List[Dict[str, Any]] = []
    for h in hits:
        ch_id = h["chunk_id"]
        pair = by_id.get(ch_id)
        if not pair:
            continue
        ch, doc = pair
        out.append(
            {
                "chunk_id": ch.id,
                "document_id": ch.document_id,
                "title": doc.title,
                "chunk_index": ch.chunk_index,
                "score": round(float(h["score"]), 6),
                "text": ch.text,
                "meta": ch.meta or {},
            }
        )

    return out
