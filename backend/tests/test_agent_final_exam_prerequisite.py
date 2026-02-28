from fastapi import HTTPException

from app.api.routes import agent as agent_route
from app.schemas.agent import FinalExamGenerateRequest


def test_final_exam_generate_blocked_when_prerequisites_not_met(monkeypatch):
    payload = FinalExamGenerateRequest(user_id=9, document_ids=[1], topics=["A"], language="vi")

    monkeypatch.setattr(
        agent_route,
        "_final_exam_prerequisite_snapshot",
        lambda db, user_id: {
            "has_graded_diagnostic_pre": False,
            "completed_tasks": 2,
            "total_tasks": 10,
            "progress": 20.0,
            "required": 70,
            "remaining_lessons": [{"day_index": 1, "task_index": 2, "title": "Ngày 1 - Bài 2", "link": "/agent-flow#topic-day-1"}],
        },
    )

    try:
        agent_route.final_exam_generate(request=None, payload=payload, db=None)
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["error"] == "PREREQUISITE_NOT_MET"
        assert exc.detail["progress"] == 20.0
        assert exc.detail["required"] == 70


def test_final_exam_generate_succeeds_when_prerequisites_met(monkeypatch):
    payload = FinalExamGenerateRequest(user_id=9, document_ids=[1], topics=["A"], language="vi")

    monkeypatch.setattr(
        agent_route,
        "_final_exam_prerequisite_snapshot",
        lambda db, user_id: {
            "has_graded_diagnostic_pre": True,
            "completed_tasks": 7,
            "total_tasks": 10,
            "progress": 70.0,
            "required": 70,
            "remaining_lessons": [],
        },
    )
    monkeypatch.setattr(
        agent_route,
        "generate_exam",
        lambda db, **kwargs: {
            "quiz_id": 123,
            "kind": "final_exam",
            "questions": [],
        },
    )

    out = agent_route.final_exam_generate(request=None, payload=payload, db=None)
    assert out["quiz_id"] == 123
    assert out["kind"] == "final_exam"
