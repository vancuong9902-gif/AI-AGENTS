from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.rag import RAGSearchRequest
from app.services.rag_service import retrieve_and_log
from app.services.corrective_rag import corrective_retrieve_and_log
from app.services import vector_store

router = APIRouter(tags=['rag'])


def _classify_semantic_rag_error(message: str) -> str:
    """Map common OpenAI/embedding failures to stable API error codes."""
    m = (message or "").lower()

    # Billing/quota issues (common during demos)
    if "insufficient_quota" in m or "exceeded your current quota" in m:
        return "INSUFFICIENT_QUOTA"

    # Missing/invalid key
    if "api key" in m and ("missing" in m or "not set" in m):
        return "OPENAI_KEY_NOT_SET"
    if "invalid_api_key" in m or "incorrect api key" in m:
        return "INVALID_API_KEY"

    # Rate-limit / too many requests
    if "rate_limit" in m or "too many requests" in m:
        return "RATE_LIMITED"

    # Fallback
    return "SEMANTIC_RAG_ERROR"


@router.post('/rag/search')
def rag_search(request: Request, payload: RAGSearchRequest, db: Session = Depends(get_db)):
    # retrieve_and_log will:
    # - use semantic search when FAISS + OPENAI_API_KEY are available and the vector index is ready
    # - otherwise fallback to keyword scoring (so the demo can run without billing)
    data = retrieve_and_log(db=db, query=payload.query, top_k=payload.top_k, filters=payload.filters.model_dump())
    return {'request_id': request.state.request_id, 'data': data, 'error': None}


@router.post('/rag/corrective_search')
def rag_corrective_search(request: Request, payload: RAGSearchRequest, db: Session = Depends(get_db)):
    """Corrective RAG: retrieve -> grade -> rewrite query -> retrieve.

    Useful when the initial retrieval is weak or the query is too generic.
    Returns the same schema as /rag/search but includes a `corrective` debug field.
    """
    data = corrective_retrieve_and_log(db=db, query=payload.query, top_k=payload.top_k, filters=payload.filters.model_dump())
    return {'request_id': request.state.request_id, 'data': data, 'error': None}

@router.post('/rag/rebuild')
def rag_rebuild(request: Request, db: Session = Depends(get_db)):
    """Rebuild FAISS index from all stored chunks.

    NOTE: This endpoint is optional.
    - If semantic RAG is disabled (no OPENAI_API_KEY / no FAISS), we return a *success* response
      with "skipped" so students can continue the flow using keyword RAG.
    """
    if not vector_store.is_enabled():
        return {
            'request_id': request.state.request_id,
            'data': {
                'rebuilt': False,
                'skipped': True,
                'reason': 'Semantic RAG is disabled. Keyword RAG (/api/rag/search) is still available.',
                'vector_status': vector_store.status(),
            },
            'error': None,
        }
    try:
        data = vector_store.rebuild_from_db(db)
        return {'request_id': request.state.request_id, 'data': data, 'error': None}
    except Exception as e:
        # Semantic RAG is optional in Docker. Return a friendly error instead of 500.
        msg = str(e)
        return {
            'request_id': request.state.request_id,
            'data': None,
            'error': {
                'code': _classify_semantic_rag_error(msg),
                'message': msg,
            },
        }

