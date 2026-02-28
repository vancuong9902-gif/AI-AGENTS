from __future__ import annotations

from typing import Any

from app.services.assessment_service import get_used_question_stems


class _FakeQuery:
    def __init__(self, rows: list[tuple[str | None]]):
        self._rows = rows

    def join(self, *_args: Any, **_kwargs: Any):
        return self

    def filter(self, *_args: Any, **_kwargs: Any):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows: list[tuple[str | None]]):
        self._rows = rows

    def query(self, *_args: Any, **_kwargs: Any):
        return _FakeQuery(self._rows)


def test_get_used_question_stems_normalizes_and_deduplicates():
    long = "What is Python? " + ("abc, " * 80)
    db = _FakeDB(
        [
            ("What is Python?",),
            ("  WHAT is python!!!   ",),
            ("",),
            (None,),
            (long,),
        ]
    )

    out = get_used_question_stems(db, user_id=7, kinds=["diagnostic_pre"])

    assert "what is python" in out
    long_norm = [x for x in out if x.startswith("what is python abc")]
    assert long_norm and len(long_norm[0]) <= 120


def test_get_used_question_stems_empty_kinds_returns_empty_set():
    db = _FakeDB([("x",)])
    assert get_used_question_stems(db, user_id=1, kinds=[]) == set()
