from __future__ import annotations

from pydantic import BaseModel


class DocumentTopicData(BaseModel):
    topic_id: int
    topic_index: int
    title: str
    display_title: str | None = None
    needs_review: bool = False
    extraction_confidence: float = 0.0
    page_range: list[int | None] = []
    summary: str
    keywords: list[str] = []
    start_chunk_index: int | None = None
    end_chunk_index: int | None = None

    # Optional richer topic profile (preview)
    outline: list[str] = []
    key_points: list[str] = []
    definitions: list[dict] = []
    examples: list[str] = []
    formulas: list[str] = []
    content_preview: str | None = None
    content_len: int | None = None
    has_more_content: bool | None = None
    included_chunk_ids: list[int] = []


class DocumentUploadData(BaseModel):
    document_id: int
    title: str
    filename: str
    mime_type: str
    chunk_count: int

    # Auto-extracted topics (Content Agent)
    topics_status: str | None = None
    topics_reason: str | None = None
    topics_quality: dict | None = None
    topics: list[DocumentTopicData] = []
