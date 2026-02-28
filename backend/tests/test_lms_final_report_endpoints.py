from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


class _FakeDB:
    pass


def _sample_report():
    return {
        "report_title": "Báo cáo tổng kết lớp học - 12A1",
        "period": {"from": "2025-01-01T00:00:00+00:00", "to": "2025-01-31T00:00:00+00:00"},
        "class_stats": {
            "total_students": 2,
            "completed_both_tests": 2,
            "avg_entry_score": 55.0,
            "avg_final_score": 70.0,
            "improvement_rate": 100.0,
            "distribution": {"gioi": 0, "kha": 2, "trung_binh": 0, "yeu": 0},
        },
        "topic_analysis": [
            {"topic": "dao_ham", "avg_score_entry": 50.0, "avg_score_final": 72.0, "mastery_rate": 75.0}
        ],
        "students": [
            {
                "user_id": 101,
                "name": "HS A",
                "level": "kha",
                "entry_score": 55.0,
                "final_score": 72.0,
                "improvement": 17.0,
                "weak_topics": ["gioi_han"],
                "ai_assessment": "Nhận xét cá nhân",
            }
        ],
        "ai_class_narrative": "Lớp có tiến bộ.",
    }


def test_get_final_report_json(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    monkeypatch.setattr("app.api.routes.lms.build_classroom_final_report", lambda db, classroom_id: _sample_report())

    client = TestClient(app)
    res = client.get("/api/lms/classroom/1/final-report")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["report_title"].startswith("Báo cáo tổng kết lớp học")
    assert data["class_stats"]["total_students"] == 2
    assert isinstance(data["students"], list)

    app.dependency_overrides.clear()


def test_get_final_report_pdf(monkeypatch, tmp_path):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    monkeypatch.setattr("app.api.routes.lms.build_classroom_final_report", lambda db, classroom_id: _sample_report())

    out_file = tmp_path / "report.pdf"
    out_file.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        "app.api.routes.lms.export_classroom_final_report_pdf",
        lambda report, classroom_id: str(out_file),
    )

    client = TestClient(app)
    res = client.get("/api/lms/classroom/1/final-report/pdf")
    assert res.status_code == 200
    assert "application/pdf" in res.headers.get("content-type", "")

    app.dependency_overrides.clear()
