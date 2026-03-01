from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.routes import documents


class FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)
        self._limit = None
        self._offset = 0

    def filter(self, *_args, **_kwargs):
        return self

    def group_by(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        self._limit = int(n)
        return self

    def offset(self, n):
        self._offset = int(n)
        return self

    def count(self):
        return len(self._rows)

    def all(self):
        start = self._offset
        end = None if self._limit is None else start + self._limit
        return self._rows[start:end]

    def first(self):
        rows = self.all()
        return rows[0] if rows else None


def _req():
    return SimpleNamespace(state=SimpleNamespace(request_id="rid-pagination"))


def test_list_document_chunks_uses_preview_and_pagination():
    chunks = [
        SimpleNamespace(id=i + 1, document_id=7, chunk_index=i, text=("A" * 500), meta={"page": 1})
        for i in range(5)
    ]

    class DB:
        def query(self, model):
            assert model.__name__ == "DocumentChunk"
            return FakeQuery(chunks)

    out = documents.list_document_chunks(_req(), document_id=7, db=DB(), limit=2, offset=1)
    data = out["data"]

    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 1
    assert len(data["items"]) == 2
    assert "text" not in data["items"][0]
    assert len(data["items"][0]["text_preview"]) == documents.CHUNK_PREVIEW_CHARS


def test_list_document_topics_pagination_total(monkeypatch):
    now = datetime.now(timezone.utc)
    doc = SimpleNamespace(id=11, content="ok")
    topics = [
        SimpleNamespace(
            id=i + 1,
            topic_index=i,
            title=f"Topic {i + 1}",
            display_title=f"Topic {i + 1}",
            status="published",
            teacher_edited_title=None,
            teacher_note=None,
            reviewed_at=now,
            needs_review=False,
            extraction_confidence=0.9,
            page_start=1,
            page_end=1,
            summary="sum",
            keywords=[],
            start_chunk_index=0,
            end_chunk_index=0,
            metadata_json={},
            quick_check_quiz_id=None,
            is_confirmed=True,
            is_active=True,
        )
        for i in range(6)
    ]

    class DB:
        def query(self, *models):
            if len(models) == 1 and getattr(models[0], "__name__", "") == "Document":
                return FakeQuery([doc])
            if len(models) == 1 and getattr(models[0], "__name__", "") == "DocumentTopic":
                return FakeQuery(topics)
            # chunk length preload query
            return FakeQuery([(0, 1000), (1, 1200)])

    monkeypatch.setattr(documents, "_text_quality_gate", lambda _text: {"status": "OK"})
    monkeypatch.setattr(documents, "topic_range_stats", lambda **_kwargs: {"chunk_span": 3, "char_len": 2000})
    monkeypatch.setattr(documents, "ensure_topic_chunk_ranges_ready_for_quiz", lambda ranges, **_kwargs: ranges)

    out = documents.list_document_topics(
        request=_req(),
        document_id=11,
        db=DB(),
        current_user=SimpleNamespace(role="teacher"),
        detail=0,
        limit=2,
        offset=2,
    )

    data = out["data"]
    assert data["total"] == 6
    assert data["limit"] == 2
    assert data["offset"] == 2
    assert len(data["items"]) == 2


def test_list_document_chunks_preview_caps_length():
    long_text = "B" * (documents.CHUNK_PREVIEW_CHARS + 123)

    class DB:
        def query(self, model):
            assert model.__name__ == "DocumentChunk"
            return FakeQuery([SimpleNamespace(id=1, document_id=9, chunk_index=0, text=long_text, meta={})])

    out = documents.list_document_chunks(_req(), document_id=9, db=DB(), limit=10, offset=0)
    item = out["data"]["items"][0]

    assert len(item["text_preview"]) == documents.CHUNK_PREVIEW_CHARS
    assert item["text_len"] == len(long_text)


def test_get_chunk_detail_returns_full_text():
    payload = SimpleNamespace(id=31, document_id=12, chunk_index=4, text="full chunk text", meta={"page": 3})

    class DB:
        def query(self, model):
            assert model.__name__ == "DocumentChunk"
            return FakeQuery([payload])

    out = documents.get_chunk_detail(_req(), chunk_id=31, db=DB())
    data = out["data"]

    assert data["chunk_id"] == 31
    assert data["document_id"] == 12
    assert data["text"] == "full chunk text"
