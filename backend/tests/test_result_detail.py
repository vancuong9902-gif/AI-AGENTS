from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services import assessment_service


class _FakeQuery:
    def __init__(self, first_value=None, all_value=None):
        self._first_value = first_value
        self._all_value = all_value if all_value is not None else []

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def first(self):
        return self._first_value

    def all(self):
        return self._all_value


class _FakeDB:
    def __init__(self, quiz_set, questions, session):
        self.quiz_set = quiz_set
        self.questions = questions
        self.session = session
        self.added = []

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "QuizSet":
            return _FakeQuery(first_value=self.quiz_set)
        if name == "Question":
            return _FakeQuery(all_value=self.questions)
        if name == "QuizSession":
            return _FakeQuery(first_value=self.session)
        if name == "ClassroomAssessment":
            return _FakeQuery(first_value=None)
        raise AssertionError(f"Unexpected model queried: {name}")

    def add(self, obj):
        if getattr(obj, "id", None) is None and obj.__class__.__name__ == "Attempt":
            obj.id = 999
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, obj):
        return None


def test_submit_assessment_includes_detail_fields_and_summary(monkeypatch):
    now = datetime.now(timezone.utc)
    quiz_set = SimpleNamespace(
        id=10,
        kind="assessment",
        topic="Đại số",
        duration_seconds=900,
        submitted_at=None,
        document_ids_json=None,
    )
    question = SimpleNamespace(
        id=101,
        quiz_set_id=10,
        order_no=1,
        type="mcq",
        stem="2 + 2 bằng mấy?",
        options=["3", "4", "5", "6"],
        correct_index=1,
        explanation="Vì 2 + 2 = 4 theo phép cộng cơ bản.",
        sources=[{"chunk_id": 1}],
        bloom_level="remember",
        max_points=1,
        rubric=None,
    )
    session = SimpleNamespace(
        quiz_set_id=10,
        user_id=7,
        started_at=now - timedelta(minutes=3),
        time_limit_seconds=900,
        submitted_at=None,
    )
    db = _FakeDB(quiz_set=quiz_set, questions=[question], session=session)

    monkeypatch.setattr(assessment_service, "ensure_user_exists", lambda *args, **kwargs: None)

    result = assessment_service.submit_assessment(
        db,
        assessment_id=10,
        user_id=7,
        answers=[{"question_id": 101, "answer_index": 1}],
    )

    row = result["breakdown"][0]
    assert row["stem"] == "2 + 2 bằng mấy?"
    assert row["options"] == ["3", "4", "5", "6"]
    assert row["difficulty"] == "easy"
    assert row["correct_answer_text"] == "4"
    assert row["student_answer_text"] == "4"

    summary = result["summary"]
    assert "by_topic" in summary
    assert "by_difficulty" in summary
    assert set(summary["by_difficulty"].keys()) == {"easy", "medium", "hard"}

    topic_bucket = summary["by_topic"][next(iter(summary["by_topic"]))]
    assert {"earned", "total", "percent"}.issubset(topic_bucket.keys())
