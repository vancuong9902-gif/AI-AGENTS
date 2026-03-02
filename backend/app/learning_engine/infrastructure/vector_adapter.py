from __future__ import annotations

from collections import defaultdict

from app.learning_engine.domain.ports import VectorIndexPort


class InMemoryVectorAdapter(VectorIndexPort):
    """Default adapter for orchestration wiring.

    In production, replace with FAISS/Chroma adapter implementation.
    """

    def __init__(self) -> None:
        self._store: dict[str, list[str]] = defaultdict(list)

    async def upsert_document_chunks(self, document_id: str, chunks: list[str]) -> None:
        self._store[document_id] = [c for c in chunks if c.strip()]

    async def semantic_search(self, query: str, top_k: int = 5) -> list[str]:
        q_words = {w.lower() for w in query.split() if w}
        scored: list[tuple[int, str]] = []
        for chunks in self._store.values():
            for chunk in chunks:
                score = sum(1 for w in q_words if w in chunk.lower())
                scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [text for _, text in scored[:top_k]]
