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


class _FakeDB:
    def query(self, *entities):
        name = ",".join(getattr(e, "name", str(e)) for e in entities)
        if "assessment_id" in name:
            return _FakeQuery([(1,), (2,)])
        if "quiz_sets.id,quiz_sets.kind" in name.replace(" ", ""):
            return _FakeQuery([(1, "diagnostic_pre"), (2, "diagnostic_post")])
        if "attempts" in name:
            return _FakeQuery(
                [
                    SimpleNamespace(user_id=101, quiz_set_id=1, breakdown_json=[]),
                    SimpleNamespace(user_id=101, quiz_set_id=2, breakdown_json=[]),
                ]
            )
        return _FakeQuery([])


def test_teacher_report_includes_narrative_and_charts(monkeypatch):
    """Endpoint trả đủ các trường mới."""

    app.dependency_overrides[get_db] = lambda: _FakeDB()

    def _fake_score_breakdown(_):
        _fake_score_breakdown.calls += 1
        if _fake_score_breakdown.calls == 1:
            return {"overall": {"percent": 45.0}, "by_topic": {"Đạo hàm": {"percent": 45.0}}}
        return {"overall": {"percent": 70.0}, "by_topic": {"Đạo hàm": {"percent": 70.0}}}

    _fake_score_breakdown.calls = 0

    monkeypatch.setattr("app.api.routes.lms.score_breakdown", _fake_score_breakdown)
    monkeypatch.setattr("app.api.routes.lms.generate_class_narrative", lambda **kwargs: "Nhận xét mẫu")

    client = TestClient(app)
    response = client.get("/api/lms/teacher/report/1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "ai_narrative" in data
    assert "weak_topics" in data
    assert "progress_chart" in data
    assert data["summary"]["students"] >= 0
    assert "avg_improvement" in data["summary"]

    app.dependency_overrides.clear()
