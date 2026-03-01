from __future__ import annotations

from types import SimpleNamespace

from app.api.routes import documents
from app.services import topic_service


def test_generate_topic_homework_json_returns_grounded_source_chunks(monkeypatch):
    chunk_context = [
        (101, "Bài tập: Tính đạo hàm của x^2."),
        (102, "Câu hỏi: Giải thích vì sao hàm số đồng biến."),
    ]

    monkeypatch.setattr(topic_service, "llm_available", lambda: True)
    monkeypatch.setattr(topic_service, "quality_report", lambda _txt: {"score": 0.9, "reasons": []})
    monkeypatch.setattr(
        topic_service,
        "chat_json",
        lambda **_kwargs: {
            "exercises": [
                {
                    "question": "Tính đạo hàm của x^2",
                    "difficulty": "easy",
                    "answer": "2x",
                    "explanation": "Áp dụng quy tắc lũy thừa",
                    "source_chunks": [101],
                },
                {
                    "question": "Nêu điều kiện đồng biến",
                    "difficulty": "medium",
                    "answer": "f'(x) > 0",
                    "explanation": "Dùng đạo hàm bậc nhất",
                    "source_chunks": [102, 999],
                },
            ]
        },
    )

    out = topic_service.generate_topic_homework_json(
        topic_id=7,
        topic_title="Đạo hàm",
        chunk_context=chunk_context,
        counts={"easy": 1, "medium": 1, "hard": 0},
    )

    assert out["status"] == "OK"
    assert len(out["exercises"]) == 2
    db_chunk_ids = {cid for cid, _ in chunk_context}
    for ex in out["exercises"]:
        assert ex["source_chunks"]
        assert set(ex["source_chunks"]).issubset(db_chunk_ids)


def test_generate_topic_homework_endpoint_only_returns_db_chunk_ids(monkeypatch):
    teacher = SimpleNamespace(id=99)
    doc = SimpleNamespace(id=11, user_id=99)
    topic = SimpleNamespace(id=21, document_id=11, title="Đạo hàm", start_chunk_index=0, end_chunk_index=1)
    chunks = [
        SimpleNamespace(id=201, document_id=11, chunk_index=0, text="Bài tập: Câu 1"),
        SimpleNamespace(id=202, document_id=11, chunk_index=1, text="Bài tập: Câu 2"),
    ]

    class _Query:
        def __init__(self, data):
            self._data = data

        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def first(self):
            if isinstance(self._data, list):
                return self._data[0] if self._data else None
            return self._data

        def all(self):
            return self._data if isinstance(self._data, list) else [self._data]

    class _DB:
        def query(self, model):
            name = getattr(model, "__name__", "")
            if name == "Document":
                return _Query(doc)
            if name == "DocumentTopic":
                return _Query(topic)
            if name == "DocumentChunk":
                return _Query(chunks)
            raise AssertionError(name)

    monkeypatch.setattr(
        documents,
        "generate_topic_homework_json",
        lambda **_kwargs: {
            "status": "OK",
            "topic_id": 21,
            "exercises": [
                {"question": "Q1", "difficulty": "easy", "answer": "A", "explanation": "E", "source_chunks": [201]},
                {"question": "Q2", "difficulty": "medium", "answer": "B", "explanation": "E", "source_chunks": [202]},
            ],
        },
    )

    req = SimpleNamespace(state=SimpleNamespace(request_id="rid-homework"))
    out = documents.generate_topic_homework(
        request=req,
        document_id=11,
        topic_id=21,
        payload={"counts": {"easy": 1, "medium": 1, "hard": 0}},
        db=_DB(),
        teacher=teacher,
    )

    assert out["request_id"] == "rid-homework"
    assert out["data"]["status"] == "OK"
    db_chunk_ids = {c.id for c in chunks}
    for ex in out["data"]["exercises"]:
        assert ex["source_chunks"]
        assert set(ex["source_chunks"]).issubset(db_chunk_ids)
