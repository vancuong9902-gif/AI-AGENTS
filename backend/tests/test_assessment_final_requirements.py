from __future__ import annotations

from typing import Any

from app.services import assessment_service


class _FakeQuery:
    def __init__(self, rows: list[tuple[Any, ...]]):
        self._rows = rows

    def filter(self, *args: Any, **kwargs: Any):
        return self

    def join(self, *args: Any, **kwargs: Any):
        return self

    def order_by(self, *args: Any, **kwargs: Any):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self):
        self.calls = 0

    def query(self, _entity: Any):
        self.calls += 1
        if self.calls == 1:
            return _FakeQuery([(10,), (11,)])  # diagnostic_pre ids
        return _FakeQuery([("Topic A",), ("Topic B",)])


def test_generate_final_exam_uses_required_structure(monkeypatch):
    captured: dict[str, Any] = {}

    def _fake_generate_assessment(db, **kwargs):
        captured.update(kwargs)
        return {"assessment_id": 1, "questions": []}

    monkeypatch.setattr(assessment_service, "generate_assessment", _fake_generate_assessment)
    db = _FakeDB()

    assessment_service.generate_final_exam(
        db,
        user_id=7,
        document_id=99,
        topic_ids=[1, 2],
        classroom_id=12,
    )

    assert captured["kind"] == "final_exam"
    assert captured["exclude_quiz_ids"] == [10, 11]
    assert captured["easy_count"] == 4
    assert captured["medium_count"] == 8
    assert captured["hard_count"] == 8
    assert captured["time_limit_minutes"] == 60
    assert captured["topics"] == ["Topic A", "Topic B"]


def test_normalize_kind_accepts_final_alias():
    assert assessment_service._normalize_assessment_kind("final") == "final_exam"
