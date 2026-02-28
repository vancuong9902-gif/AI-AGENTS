from __future__ import annotations

from typing import Any

from app.services.assessment_service import get_used_question_stems


class _FakeQuery:
    def __init__(self, rows: list[tuple[str]]):
        self._rows = rows
        self.filters: list[Any] = []

    def join(self, *_args: Any, **_kwargs: Any):
        return self

    def filter(self, *criteria: Any):
        self.filters.extend(criteria)
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows: list[tuple[str]]):
        self._rows = rows

    def query(self, _entity: Any):
        return _FakeQuery(self._rows)


def test_get_used_question_stems_normalizes_and_truncates():
    db = _FakeDB(
        [
            (" What is Python programming language??? ",),
            ("what is python programming language",),
            ("A" * 200,),
            ("",),
            (None,),
        ]
    )

    stems = get_used_question_stems(db, user_id=7, kinds=["diagnostic_pre"])

    assert "what is python programming language" in stems
    assert len([s for s in stems if s.startswith("what is python")]) == 1
    assert any(len(s) == 120 for s in stems)


def test_get_used_question_stems_empty_kinds_returns_empty_set():
    db = _FakeDB([("foo",)])
    assert get_used_question_stems(db, user_id=7, kinds=[]) == set()
