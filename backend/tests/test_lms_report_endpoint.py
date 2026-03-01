from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.services import lms_service


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
    lms_service._TEACHER_REPORT_CACHE.clear()

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


def test_teacher_report_contains_new_ai_structure(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    lms_service._TEACHER_REPORT_CACHE.clear()

    def _fake_score_breakdown(_):
        _fake_score_breakdown.calls += 1
        if _fake_score_breakdown.calls == 1:
            return {"overall": {"percent": 50.0}, "by_topic": {"ham_so": {"percent": 50.0}}}
        return {"overall": {"percent": 80.0}, "by_topic": {"ham_so": {"percent": 80.0}}}

    _fake_score_breakdown.calls = 0
    monkeypatch.setattr("app.services.lms_service.score_breakdown", _fake_score_breakdown)
    monkeypatch.setattr(
        "app.services.lms_service._build_student_ai_evaluation",
        lambda student_data: {
            "summary": "Có tiến bộ.",
            "strengths": ["Nắm kiến thức cơ bản"],
            "improvements": ["Luyện thêm bài nâng cao"],
            "recommendation": "Ôn 30 phút mỗi ngày",
        },
    )

    async def _fake_comment(_stats):
        return "Nhận xét lớp tổng quan"

    monkeypatch.setattr("app.services.lms_service.generate_class_ai_comment", _fake_comment)

    client = TestClient(app)
    response = client.get("/api/lms/teacher/report/1")
    assert response.status_code == 200
    data = response.json()["data"]

    assert "students" in data
    assert "class_summary" in data
    assert data["students"][0]["ai_evaluation"]["summary"] == "Có tiến bộ."
    assert "overall_assessment" in data["class_summary"]

    app.dependency_overrides.clear()


def test_teacher_report_export_html_v1(monkeypatch):
    class _CountQuery:
        def filter(self, *args, **kwargs):
            return self

        def count(self):
            return 1

    class _DB:
        def query(self, *entities):
            return _CountQuery()

    app.dependency_overrides[get_db] = lambda: _DB()

    monkeypatch.setattr(
        "app.api.routes.lms.build_teacher_report",
        lambda db, classroom_id: {
            "classroom_id": classroom_id,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "students": [
                {
                    "name": "HS A",
                    "diagnostic_score": 50.0,
                    "final_score": 70.0,
                    "improvement_pct": 20.0,
                    "level": "kha",
                    "topic_scores": {"ham_so": 70.0},
                    "ai_evaluation": {"summary": "Tiến bộ tốt."},
                }
            ],
            "class_summary": {
                "avg_improvement": 20.0,
                "top_performers": ["HS A"],
                "needs_attention": [],
                "overall_assessment": "Tổng quan tích cực",
            },
        },
    )

    client = TestClient(app)
    response = client.get("/api/v1/lms/teacher/report/1/export?format=html")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "HS A" in response.text

    app.dependency_overrides.clear()


def test_teacher_report_contains_per_student_and_topic_heatmap(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    from app.api.routes import lms as lms_route
    lms_route._report_cache.clear()
    lms_route._report_cache_time.clear()

    monkeypatch.setattr(
        "app.api.routes.lms.generate_full_teacher_report",
        lambda classroom_id, db: {
            "classroom_id": classroom_id,
            "summary": {"total_students": 1},
            "per_student": [{"student_id": 101, "name": "HS A", "improvement": 12}],
            "topic_heatmap": [{"topic": "dao_ham", "avg_score": 72.0, "students": 1}],
        },
    )

    client = TestClient(app)
    response = client.get("/api/lms/teacher/report/1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "per_student" in data
    assert "topic_heatmap" in data
    assert data["per_student"][0]["name"] == "HS A"

    app.dependency_overrides.clear()
