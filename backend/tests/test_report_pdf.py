from pathlib import Path
from types import SimpleNamespace

from app.services import report_pdf_service


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def query(self, model, *args):
        name = getattr(model, "__name__", "")
        if name == "User":
            return _Query([SimpleNamespace(id=11, full_name="Nguyễn Văn A")])
        if name == "Classroom":
            return _Query([SimpleNamespace(id=3, name="Lớp 10A1")])
        if name == "LearnerProfile":
            return _Query([SimpleNamespace(user_id=11, mastery_json={"Hàm số": "kha", "Hình học": "yeu"})])
        return _Query([])


def test_generate_classroom_report_pdf(monkeypatch):
    monkeypatch.setattr(
        report_pdf_service,
        "generate_full_teacher_report",
        lambda classroom_id, db: {
            "classroom_name": "Lớp 10A1",
            "summary": {"total_students": 2, "students_with_final": 2, "avg_improvement": 8.5},
            "per_student": [
                {"student_id": 1, "student_name": "A", "placement_score": 45.0, "final_score": 70.0},
                {"student_id": 2, "student_name": "B", "placement_score": 55.0, "final_score": 78.0},
            ],
            "ai_class_narrative": "Lớp tiến bộ tốt.",
        },
    )
    monkeypatch.setattr(report_pdf_service, "_latest_pre_post_attempts", lambda db, classroom_id, student_id: (None, None))
    monkeypatch.setattr(report_pdf_service, "analyze_topic_weak_points", lambda _: [{"topic": "Hình học", "avg_pct": 52.0, "weak_count": 1, "total": 2, "suggestion": "Ôn tập thêm"}])

    out = report_pdf_service.generate_classroom_report_pdf(db=object(), classroom_id=3)
    assert isinstance(out, Path)
    assert out.exists()
    assert out.stat().st_size > 0


def test_generate_student_report_pdf(monkeypatch):
    monkeypatch.setattr(
        report_pdf_service,
        "_latest_pre_post_attempts",
        lambda db, classroom_id, student_id: (
            SimpleNamespace(score_percent=40.0, breakdown_json=[]),
            SimpleNamespace(score_percent=82.0, breakdown_json=[]),
        ),
    )
    monkeypatch.setattr(
        report_pdf_service,
        "build_recommendations",
        lambda breakdown, document_topics: [
            {"topic": "Hình học", "material": "Ôn định lý", "exercise": "Làm 10 câu cơ bản"}
        ],
    )

    out = report_pdf_service.generate_student_report_pdf(db=_FakeDB(), classroom_id=3, student_id=11)
    assert isinstance(out, Path)
    assert out.exists()
    assert out.stat().st_size > 0
