from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_db, require_teacher
from app.main import app


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def query(self, *entities):
        if entities and getattr(entities[0], "__name__", "") == "Classroom":
            return _FakeQuery([SimpleNamespace(id=1, teacher_id=7, name="12A1")])
        return _FakeQuery([])


def test_export_latest_report_pdf(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    app.dependency_overrides[require_teacher] = lambda: SimpleNamespace(id=7, full_name="GV A")

    monkeypatch.setattr(
        "app.api.routes.classrooms._build_latest_report_data",
        lambda db, classroom_id: {
            "narrative": "Nhận xét",
            "level_dist": {"gioi": 1, "kha": 1, "trung_binh": 0, "yeu": 0},
            "weak_topics": [],
            "students": [],
            "improvement": {"avg_delta": 0.0, "improved_count": 0},
        },
    )

    def _fake_export(report_data, output_path, *, class_name, teacher_name):
        with open(output_path, "wb") as f:
            f.write(b"%PDF-1.4\n")
        return output_path

    monkeypatch.setattr("app.api.routes.classrooms.export_class_report_pdf", _fake_export)

    client = TestClient(app)
    res = client.get("/api/classrooms/1/reports/latest/export?format=pdf")
    assert res.status_code == 200
    assert "application/pdf" in res.headers.get("content-type", "")

    app.dependency_overrides.clear()


def test_export_latest_report_docx(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    app.dependency_overrides[require_teacher] = lambda: SimpleNamespace(id=7, full_name="GV A")

    monkeypatch.setattr(
        "app.api.routes.classrooms._build_latest_report_data",
        lambda db, classroom_id: {
            "narrative": "Nhận xét",
            "level_dist": {"gioi": 1, "kha": 1, "trung_binh": 0, "yeu": 0},
            "weak_topics": [],
            "students": [],
            "improvement": {"avg_delta": 0.0, "improved_count": 0},
        },
    )

    def _fake_export(report_data, output_path, *, class_name, teacher_name):
        with open(output_path, "wb") as f:
            f.write(b"PK\x03\x04")
        return output_path

    monkeypatch.setattr("app.api.routes.classrooms.export_class_report_docx", _fake_export)

    client = TestClient(app)
    res = client.get("/api/classrooms/1/reports/latest/export?format=docx")
    assert res.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in res.headers.get("content-type", "")

    app.dependency_overrides.clear()


def test_export_teacher_classroom_pdf(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    app.dependency_overrides[require_teacher] = lambda: SimpleNamespace(id=7, full_name="GV A")

    monkeypatch.setattr(
        "app.api.routes.classrooms._build_export_students",
        lambda db, classroom_id: [
            {
                "name": "Nguyễn Văn A",
                "email": "a@example.com",
                "placement_score": 60,
                "final_score": 85,
                "level": "kha",
                "study_hours": 12,
                "ai_comment": "Tiến bộ tốt",
            }
        ],
    )
    monkeypatch.setattr(
        "app.api.routes.classrooms.generate_class_report_pdf",
        lambda classroom_data, students_data: b"%PDF-1.4\n",
    )

    client = TestClient(app)
    res = client.get("/api/teacher/classrooms/1/report/pdf")
    assert res.status_code == 200
    assert "application/pdf" in res.headers.get("content-type", "")

    app.dependency_overrides.clear()


def test_export_teacher_classroom_excel(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    app.dependency_overrides[require_teacher] = lambda: SimpleNamespace(id=7, full_name="GV A")

    monkeypatch.setattr(
        "app.api.routes.classrooms._build_export_students",
        lambda db, classroom_id: [
            {
                "name": "Nguyễn Văn A",
                "email": "a@example.com",
                "placement_score": 60,
                "final_score": 85,
                "level": "kha",
                "study_hours": 12,
                "ai_comment": "Tiến bộ tốt",
            }
        ],
    )
    monkeypatch.setattr(
        "app.api.routes.classrooms.generate_class_report_excel",
        lambda classroom_data, students_data: b"PK\x03\x04",
    )

    client = TestClient(app)
    res = client.get("/api/teacher/classrooms/1/report/excel")
    assert res.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res.headers.get("content-type", "")

    app.dependency_overrides.clear()
