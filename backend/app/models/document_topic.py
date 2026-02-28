from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class DocumentTopic(Base):
    """Auto-extracted topics from a teacher uploaded document.

    We keep this lightweight so the demo UI can present 'topics' immediately after upload,
    and other endpoints can later filter RAG/quiz generation by topic.
    """

    __tablename__ = "document_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True, nullable=False)

    topic_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # Optional chunk-range mapping (by chunk_index). Helps later: filter chunks for a topic.
    start_chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
