from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import assessment_service


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self, quiz_set, attempt, questions):
        self.quiz_set = quiz_set
        self.attempt = attempt
        self.questions = questions

    def query(self, model, *_args, **_kwargs):
        name = getattr(model, "__name__", "")
        if name == "QuizSet":
            return _FakeQuery([self.quiz_set])
        if name == "Attempt":
            return _FakeQuery([self.attempt])
        if name == "Question":
            return _FakeQuery(self.questions)
        raise AssertionError(f"Unexpected query model: {name}")

    def add(self, _obj):
        return None

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def test_get_or_generate_attempt_explanations_persists_map(monkeypatch):
    quiz = SimpleNamespace(id=11, kind="midterm", document_ids_json=None)
    attempt = SimpleNamespace(
        id=99,
        user_id=7,
        quiz_set_id=11,
        created_at=datetime.now(timezone.utc),
        breakdown_json=[
            {
                "question_id": 101,
                "type": "mcq",
                "score_points": 0,
                "max_points": 1,
                "chosen": 1,
                "correct": 2,
                "is_correct": False,
            }
        ],
        explanation_json=None,
    )
    questions = [
        SimpleNamespace(
            id=101,
            quiz_set_id=11,
            order_no=1,
            type="mcq",
            stem="2 + 3 = ?",
            options=["4", "6", "5"],
            correct_index=2,
            sources=[],
        )
    ]

    db = _FakeDB(quiz_set=quiz, attempt=attempt, questions=questions)

    monkeypatch.setattr(assessment_service, "flag_modified", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        assessment_service,
        "_generate_mcq_explanation_map",
        lambda *_args, **_kwargs: {"101": "Đáp án đúng là 5 vì phép cộng 2 + 3 bằng 5."},
    )

    out = assessment_service.get_or_generate_attempt_explanations(
        db,
        assessment_id=11,
        user_id=7,
        attempt_id=99,
    )

    assert out["101"]
    assert attempt.explanation_json == {"101": "Đáp án đúng là 5 vì phép cộng 2 + 3 bằng 5."}
