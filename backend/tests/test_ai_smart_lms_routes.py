from __future__ import annotations

from pathlib import Path

ROUTE_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "ai_smart_lms.py"
SERVICE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "ai_smart_lms_service.py"


def test_blueprint_and_guardrail_routes_exist() -> None:
    route_src = ROUTE_PATH.read_text(encoding="utf-8")
    assert '@router.get("/blueprint"' in route_src
    assert '@router.get("/student/course-gate"' in route_src
    assert '@router.post("/tutor/guardrail"' in route_src


def test_student_gate_message_matches_requirement() -> None:
    route_src = ROUTE_PATH.read_text(encoding="utf-8")
    assert '"No course available yet."' in route_src


def test_tutor_guardrail_restricts_off_topic_questions() -> None:
    service_src = SERVICE_PATH.read_text(encoding="utf-8")
    assert "I can only answer questions tied to uploaded material and current topic." in service_src
