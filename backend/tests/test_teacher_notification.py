from types import SimpleNamespace

from app.api.routes import lms
from app.models.notification import Notification


class _Q:
    def __init__(self, entity, db):
        self.entity = entity
        self.db = db

    def join(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        return self

    def distinct(self):
        return self

    def limit(self, _n):
        return self

    def all(self):
        name = getattr(self.entity, "__name__", str(self.entity))
        if "ClassroomMember.user_id" in str(self.entity):
            return [(11,), (12,)]
        if "Attempt.user_id" in str(self.entity):
            return [(11,), (12,)]
        if name == "Notification":
            return []
        return []

    def count(self):
        return 0

    def first(self):
        name = getattr(self.entity, "__name__", str(self.entity))
        if name == "Session":
            return SimpleNamespace(id=1, user_id=11, type="quiz_attempt:99", started_at=None)
        if name == "QuizSet":
            return SimpleNamespace(id=99, kind="diagnostic_post", topic="", duration_seconds=1800, classroom_id=1, document_ids_json=[])
        if "ClassroomAssessment" in name:
            return SimpleNamespace(id=1, classroom_id=1)
        if name == "Classroom":
            return SimpleNamespace(id=1, teacher_id=7)
        if name == "Notification":
            return None
        return SimpleNamespace(id=1)


class _DB:
    def __init__(self):
        self.added = []

    def query(self, entity):
        return _Q(entity, self)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, _obj):
        pass


def test_submit_attempt_post_creates_report_ready_notification(monkeypatch):
    db = _DB()
    req = SimpleNamespace(state=SimpleNamespace(request_id="r1"))
    payload = lms.SubmitAttemptByIdIn(answers=[])

    monkeypatch.setattr(lms, "submit_assessment", lambda *a, **k: {"breakdown": [], "total_score_percent": 88})
    monkeypatch.setattr(lms, "score_breakdown", lambda _x: {"overall": {"percent": 88.0}, "weak_topics": []})
    monkeypatch.setattr(lms, "classify_student_level", lambda _x: {"level_key": "gioi"})
    monkeypatch.setattr(lms, "classify_student_multidim", lambda **k: {})
    monkeypatch.setattr(lms, "build_recommendations", lambda **k: [])
    monkeypatch.setattr(lms, "assign_learning_path", lambda *a, **k: {"plan_id": 1})
    monkeypatch.setattr(lms, "notify_teacher_student_finished", lambda *a, **k: None)

    out = lms.submit_attempt_by_id(req, 1, payload, db)
    assert out["error"] is None
    assert any(isinstance(x, Notification) and (getattr(x.type, "value", x.type) == "report_ready") for x in db.added)
