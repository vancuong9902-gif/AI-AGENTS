from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def count(self):
        return len(self._rows)


class _FakeDB:
    def query(self, *entities):
        dump = ",".join(str(x).lower() for x in entities)
        now = datetime.now(timezone.utc)
        if "quizset.id" in dump and "quizset.kind" in dump:
            return _FakeQuery([(1, "diagnostic_pre"), (2, "diagnostic_post")])
        if "classroom" in dump and "classroom.id" in dump:
            return _FakeQuery([SimpleNamespace(id=1, teacher_id=999, name="A")])
        if "classroommember" in dump:
            return _FakeQuery([SimpleNamespace(user_id=101), SimpleNamespace(user_id=102)])
        if "attempt" in dump:
            return _FakeQuery([SimpleNamespace(score_percent=40, breakdown_json=[], created_at=now)])
        if "learningplan" in dump:
            return _FakeQuery([SimpleNamespace(id=1, days_total=5, created_at=now)])
        if "learningplantaskcompletion" in dump:
            return _FakeQuery([SimpleNamespace(id=1), SimpleNamespace(id=2)])
        if "learningplanhomeworksubmission" in dump:
            return _FakeQuery([SimpleNamespace(id=1)])
        if "session" in dump:
            return _FakeQuery([SimpleNamespace(id=1)])
        return _FakeQuery([])


def test_teacher_report_returns_enhanced_shape(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    monkeypatch.setattr("app.api.routes.lms.resolve_student_name", lambda _db, uid: f"HS {uid}")
    monkeypatch.setattr("app.api.routes.lms.llm_available", lambda: False)
    monkeypatch.setattr("app.api.routes.lms.analyze_topic_weak_points", lambda _x: [{"topic": "ham_so", "wrong": 3}])
    monkeypatch.setattr("app.api.routes.lms.score_breakdown", lambda _x: {"by_topic": {"ham_so": {"percent": 45.0}}})

    client = TestClient(app)
    resp = client.get("/api/lms/teacher/report/1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) >= {"classroom_id", "generated_at", "class_summary", "per_student", "topic_heatmap", "ai_class_narrative", "recommendations_for_teacher"}
    assert isinstance(data["per_student"], list)
    assert set(data["per_student"][0].keys()) >= {"placement_score", "final_score", "improvement", "weak_topics", "strong_topics", "homework_completion_rate", "tutor_sessions_count", "ai_comment"}

    app.dependency_overrides.clear()
