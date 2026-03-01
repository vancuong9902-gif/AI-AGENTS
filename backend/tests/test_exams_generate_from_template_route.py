from __future__ import annotations

from app.api.routes import exams
from app.schemas.exam import ExamGenerateFromTemplateRequest


class _DummyDB:
    pass


def test_generate_from_template_returns_ok_and_assessment_id(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_generate_assessment(db, **kwargs):
        captured.update(kwargs)
        return {"assessment_id": 321, "title": kwargs.get("title")}

    monkeypatch.setattr(exams.assessment_service, "generate_assessment", _fake_generate_assessment)

    payload = ExamGenerateFromTemplateRequest(
        template_id="posttest_standard",
        teacher_id=1,
        classroom_id=2,
        title="Final theo template",
        level="intermediate",
        document_ids=[9],
        topics=["python"],
    )

    out = exams.generate_from_template(payload=payload, db=_DummyDB())

    assert out["status"] == "ok"
    assert out["data"]["assessment_id"] == 321
    assert captured["teacher_id"] == 1
    assert captured["classroom_id"] == 2
    assert captured["medium_count"] == 10
    assert captured["hard_mcq_count"] == 6
    assert captured["hard_count"] == 3
