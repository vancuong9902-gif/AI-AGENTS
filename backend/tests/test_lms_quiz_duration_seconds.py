from __future__ import annotations

from types import SimpleNamespace

from app.api.routes import lms


class _FakeQuery:
    def __init__(self, entity, db):
        self.entity = entity
        self.db = db

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        if self.entity is lms.DocumentTopic.title:
            return [("Algebra",), ("Geometry",)]
        return []

    def first(self):
        if self.entity is lms.QuizSet:
            return self.db.quiz
        return None


class _FakeDB:
    def __init__(self):
        self.quiz = SimpleNamespace(id=11, level="intermediate", duration_seconds=1800)
        self.committed = False

    def query(self, entity):
        return _FakeQuery(entity, self)

    def commit(self):
        self.committed = True


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(request_id="req-1"))


def test_create_placement_quiz_persists_duration_seconds(monkeypatch):
    db = _FakeDB()

    monkeypatch.setattr(
        lms,
        "_generate_assessment_lms",
        lambda **kwargs: {"request_id": "req-1", "data": {"assessment_id": 11}, "error": None},
    )

    payload = lms.PlacementQuizIn(topic_ids=[1], duration_seconds=3600)
    resp = lms.create_placement_quiz(request=_request(), payload=payload, db=db)

    assert db.committed is True
    assert db.quiz.duration_seconds == 3600
    assert db.quiz.level == "intermediate"
    assert "duration=" not in db.quiz.level
    assert int(resp["data"]["duration_seconds"]) == 3600
    assert lms._quiz_duration_map(db.quiz) == 3600


def test_create_final_quiz_persists_duration_seconds(monkeypatch):
    db = _FakeDB()

    monkeypatch.setattr(
        lms,
        "_generate_assessment_lms",
        lambda **kwargs: {"request_id": "req-1", "data": {"assessment_id": 11}, "error": None},
    )

    payload = lms.PlacementQuizIn(topic_ids=[1], duration_seconds=3600)
    resp = lms.create_final_quiz(request=_request(), payload=payload, db=db)

    assert db.committed is True
    assert db.quiz.duration_seconds == 3600
    assert db.quiz.level == "intermediate"
    assert "duration=" not in db.quiz.level
    assert int(resp["data"]["duration_seconds"]) == 3600
    assert lms._quiz_duration_map(db.quiz) == 3600
