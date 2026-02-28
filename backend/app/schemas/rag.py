from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RAGFilters(BaseModel):
    document_ids: Optional[List[int]] = None
    tags: Optional[List[str]] = None


class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: RAGFilters = Field(default_factory=RAGFilters)


class ChunkOut(BaseModel):
    chunk_id: int
    document_id: int
    title: Optional[str] = None
    chunk_index: int
    score: float
    text: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class RAGSearchData(BaseModel):
    mode: str = Field(description="retrieval mode used: hybrid|semantic|keyword")
    query_id: int
    query: str
    top_k: int
    chunks: List[ChunkOut]
