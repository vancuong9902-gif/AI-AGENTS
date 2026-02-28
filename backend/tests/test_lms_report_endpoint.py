from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows

    def order_by(self, *args, **kwargs):
        return self


class _FakeDB:
    def query(self, *entities):
        entity_dump = ",".join(str(e).lower() for e in entities)
        if "classroommember.user_id" in entity_dump:
            return _FakeQuery([(101,), (102,)])
        if "classroomassessment.assessment_id" in entity_dump:
            return _FakeQuery([(1,), (2,)])
        if "quizset.id" in entity_dump and "quizset.kind" in entity_dump:
            return _FakeQuery([(1, "diagnostic_pre"), (2, "diagnostic_post")])
        if "attempt" in entity_dump:
            return _FakeQuery(
                [
                    SimpleNamespace(user_id=101, quiz_set_id=1, breakdown_json=[], created_at=datetime.now(timezone.utc)),
                    SimpleNamespace(user_id=101, quiz_set_id=2, breakdown_json=[], created_at=datetime.now(timezone.utc)),
                ]
            )
        if "user.id" in entity_dump:
            return _FakeQuery([SimpleNamespace(id=101, full_name="HS A", email="a@test")])
        if "learningplan" in entity_dump:
            return _FakeQuery([SimpleNamespace(user_id=101, days_total=5)])
        if "learningplanhomeworksubmission" in entity_dump:
            return _FakeQuery([SimpleNamespace(user_id=101, created_at=datetime.now(timezone.utc))])
        return _FakeQuery([])


def test_teacher_report_returns_full_shape(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()

    def _fake_score_breakdown(_):
        _fake_score_breakdown.calls += 1
        if _fake_score_breakdown.calls == 1:
            return {"overall": {"percent": 45.0}, "by_topic": {"dao_ham": {"percent": 45.0}}}
        return {"overall": {"percent": 70.0}, "by_topic": {"dao_ham": {"percent": 70.0}}}

    _fake_score_breakdown.calls = 0
    monkeypatch.setattr("app.services.lms_service.score_breakdown", _fake_score_breakdown)
    async def _fake_comment(_stats):
        return "Lớp có tiến bộ tốt."

    monkeypatch.setattr("app.services.lms_service.generate_class_ai_comment", _fake_comment)

    client = TestClient(app)
    response = client.get("/api/lms/teacher/report/1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["classroom_id"] == 1
    assert "generated_at" in data
    assert "summary" in data
    assert "student_list" in data
    assert "class_analytics" in data
    assert "ai_recommendations" in data
    assert data["summary"]["total_students"] == 2
    assert set(data["class_analytics"]["score_distribution"].keys()) == {"gioi", "kha", "trung_binh", "yeu"}

    app.dependency_overrides.clear()
