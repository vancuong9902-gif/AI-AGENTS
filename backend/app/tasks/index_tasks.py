from __future__ import annotations

from typing import Any, Dict, Optional

from app.db.session import SessionLocal
from app.services import vector_store
from app.models.document_chunk import DocumentChunk


def task_index_document(document_id: int) -> Dict[str, Any]:
    """Background: embed + add chunks for a document into FAISS.

    - Safe to call multiple times (vector_store.add_chunks does basic dedup by hash).
    - If semantic RAG disabled, returns skipped.
    """
    if not vector_store.is_enabled():
        return {"indexed": False, "skipped": True, "reason": "semantic_rag_disabled"}

    vector_store.load_if_exists()

    db = SessionLocal()
    try:
        rows = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == int(document_id))
            .order_by(DocumentChunk.id.asc())
            .all()
        )
        payload = [{"chunk_id": int(r.id), "document_id": int(r.document_id), "text": str(r.text or "")} for r in rows]
        info = vector_store.add_chunks(payload)
        return {"indexed": True, "document_id": int(document_id), **info}
    finally:
        db.close()


def task_rebuild_vector_index() -> Dict[str, Any]:
    """Background: full rebuild (expensive)."""
    if not vector_store.is_enabled():
        return {"rebuilt": False, "skipped": True, "reason": "semantic_rag_disabled"}

    vector_store.load_if_exists()

    db = SessionLocal()
    try:
        info = vector_store.rebuild_from_db(db)
        return {"rebuilt": True, **info}
    finally:
        db.close()
