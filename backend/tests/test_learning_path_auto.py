from __future__ import annotations

from types import SimpleNamespace

from app.api.routes import lms


class _Query:
    def __init__(self, entity, state):
        self.entity = entity
        self.state = state

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return []

    def first(self):
        name = getattr(self.entity, "__name__", "")
        if name == "Session":
            return SimpleNamespace(id=1, user_id=11, type="quiz_attempt:99", started_at=None)
        if name == "QuizSet":
            return SimpleNamespace(id=99, kind="diagnostic_pre", topic="Đại số", duration_seconds=1800, classroom_id=3, document_ids_json=None)
        if name == "ClassroomAssessment":
            return SimpleNamespace(classroom_id=3)
        if name == "LearningPlan":
            return self.state.get("plan")
        return None


class _DB:
    def __init__(self):
        self.state = {}

    def query(self, entity):
        return _Query(entity, self.state)

    def add(self, _obj):
        return None

    def commit(self):
        return None


def test_submit_attempt_by_id_auto_creates_learning_plan(monkeypatch):
    monkeypatch.setattr(lms, "submit_assessment", lambda *args, **kwargs: {"breakdown": [{"topic": "Đại số", "max_points": 10, "score_points": 4}]})
    monkeypatch.setattr(lms, "score_breakdown", lambda _x: {"overall": {"percent": 40.0}, "by_topic": {"Đại số": {"percent": 40.0}}})
    monkeypatch.setattr(lms, "classify_student_level", lambda _x: {"level_key": "yeu", "label": "Yếu"})
    monkeypatch.setattr(lms, "classify_student_multidim", lambda **kwargs: {})
    monkeypatch.setattr(lms, "build_recommendations", lambda **kwargs: [])
    monkeypatch.setattr(lms, "_publish_mas_event_non_blocking", lambda *args, **kwargs: None)

    captured = {}

    def _fake_assign(_db, **kwargs):
        captured["called"] = True
        captured["kwargs"] = kwargs
        return {"plan_id": 555}

    monkeypatch.setattr(lms, "assign_learning_path", _fake_assign)
    monkeypatch.setattr(lms, "_upsert_plan_weak_topics", lambda *_args, **_kwargs: None)

    req = SimpleNamespace(state=SimpleNamespace(request_id="rid"))
    out = lms.submit_attempt_by_id(req, 1, lms.SubmitAttemptByIdIn(answers=[]), _DB())

    assert captured.get("called") is True
    assert out["data"]["learning_path_assigned"] is True
    assert out["data"]["learning_plan_id"] == 555


def test_assign_learning_path_yeu_no_body_len_crash():
    class _Topic:
        def __init__(self, tid, title, summary, start_chunk_index=None, end_chunk_index=None):
            self.id = tid
            self.title = title
            self.summary = summary
            self.document_id = 10
            self.topic_index = tid
            self.start_chunk_index = start_chunk_index
            self.end_chunk_index = end_chunk_index

    class _Q:
        def __init__(self, model, db):
            self.model = model
            self.db = db

        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return list(self.db.topics)

        def first(self):
            from app.models.quiz_set import QuizSet
            from app.models.learner_profile import LearnerProfile
            from app.models.learning_plan import LearningPlan

            if self.model is QuizSet:
                return SimpleNamespace(id=900, level="beginner")
            if self.model is LearnerProfile:
                return None
            if self.model is LearningPlan:
                return None
            return None

    class _FakeDB:
        def __init__(self):
            self.topics = [
                _Topic(1, "A", "x" * 1000, 1, 5),
                _Topic(2, "B", "x" * 100),
                _Topic(3, "C", "x" * 200, 6, 6),
            ]

        def query(self, model):
            return _Q(model, self)

        def add(self, _obj):
            return None

        def commit(self):
            return None

        def refresh(self, _obj):
            return None

    out = lms.assign_learning_path(_FakeDB(), user_id=1, student_level="yeu", document_ids=[10], classroom_id=1)
    assert out["total_assigned"] > 0
