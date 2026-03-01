from __future__ import annotations

from types import SimpleNamespace

from app.api.routes import lms
from app.models.classroom_assessment import ClassroomAssessment


def test_quiz_duration_map_uses_duration_seconds():
    quiz = SimpleNamespace(duration_seconds=900, level="intermediate;duration=120")
    assert lms._quiz_duration_map(quiz) == 900


class _Q:
    def __init__(self, entity):
        self.entity = entity

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *criteria):
        self.criteria = criteria
        return self

    def distinct(self):
        return self

    def all(self):
        if self.entity is ClassroomAssessment.assessment_id:
            return [(11,), (12,)]
        return []


class _DB:
    def query(self, entity):
        return _Q(entity)


def test_lms_generate_final_uses_classroom_assessment_ids(monkeypatch):
    db = _DB()
    payload = lms.GenerateLmsQuizIn(teacher_id=1, classroom_id=9)
    req = SimpleNamespace(state=SimpleNamespace(request_id="r1"))

    monkeypatch.setattr(
        lms,
        "generate_assessment",
        lambda *args, **kwargs: {"assessment_id": 77, "exclude_quiz_ids": kwargs.get("exclude_quiz_ids")},
    )

    out = lms.lms_generate_final(req, payload, db)
    assert out["data"]["excluded_from_count"] == 2


def test_submit_attempt_by_id_publishes_entry_event(monkeypatch):
    class _Query2:
        def __init__(self, entity):
            self.entity = entity

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            if self.entity.__name__ == "Session":
                return SimpleNamespace(id=1, user_id=5, type="quiz_attempt:99", started_at=None)
            return SimpleNamespace(id=99, kind="diagnostic_pre", topic="A", duration_seconds=1800, classroom_id=2)

    class _DB2:
        def query(self, entity):
            return _Query2(entity)

    monkeypatch.setattr(lms, "submit_assessment", lambda *args, **kwargs: {"breakdown": []})
    monkeypatch.setattr(lms, "score_breakdown", lambda _x: {"overall": {"percent": 80.0}, "weak_topics": []})
    monkeypatch.setattr(lms, "classify_student_level", lambda _x: "kha")
    monkeypatch.setattr(lms, "classify_student_multidim", lambda **kwargs: {})
    monkeypatch.setattr(lms, "build_recommendations", lambda **kwargs: [])

    captured = {}
    monkeypatch.setattr(lms, "_publish_mas_event_non_blocking", lambda *_args, **kwargs: captured.setdefault("event", kwargs.get("event")))

    req = SimpleNamespace(state=SimpleNamespace(request_id="rid"))
    payload = lms.SubmitAttemptByIdIn(answers=[])
    out = lms.submit_attempt_by_id(req, 1, payload, _DB2())
    assert out["data"]["classification"] == "kha"
    assert captured["event"].type == "ENTRY_TEST_SUBMITTED"
