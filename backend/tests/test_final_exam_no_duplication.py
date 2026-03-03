from __future__ import annotations

from typing import Any

from app.services import lms_service


class _FakeQuery:
    def __init__(self, rows: list[tuple[Any, ...]]):
        self._rows = rows

    def join(self, *args: Any, **kwargs: Any):
        return self

    def filter(self, *args: Any, **kwargs: Any):
        return self

    def distinct(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self):
        self.calls = 0

    def query(self, _entity: Any):
        self.calls += 1
        if self.calls == 1:
            return _FakeQuery([(1,), (2,), (3,)])  # learner attempts
        if self.calls == 2:
            return _FakeQuery([(3,), (4,)])  # assigned to learner classroom
        return _FakeQuery([])


def test_final_does_not_repeat_placement_questions(monkeypatch):
    captured: dict[str, Any] = {}

    def _fake_generate_assessment(db, **kwargs):
        captured.update(kwargs)
        return {"assessment_id": 9, "questions": []}

    monkeypatch.setattr("app.services.assessment_service.generate_assessment", _fake_generate_assessment)

    out = lms_service.generate_final_exam(
        _FakeDB(),
        teacher_user_id=99,
        learner_user_id=7,
        classroom_id=11,
        document_ids=[77],
        topics=["Đại số", "Hình học"],
    )

    assert captured["exclude_quiz_ids"] == [1, 2, 3, 4]
    assert captured["dedup_user_id"] == 7
    assert captured["attempt_user_id"] == 7
    assert captured["similarity_threshold"] == 0.75
    assert out["excluded_from_count"] == 4
