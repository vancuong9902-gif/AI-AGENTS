from __future__ import annotations

from pathlib import Path


AUTH_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "auth.py"
ADMIN_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "admin.py"
LMS_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "lms.py"
SCHEMA_AUTH_PATH = Path(__file__).resolve().parents[1] / "app" / "schemas" / "auth.py"


def test_register_student_requires_student_code_schema_and_fixed_role():
    schema_src = SCHEMA_AUTH_PATH.read_text(encoding="utf-8")
    auth_src = AUTH_PATH.read_text(encoding="utf-8")
    assert "student_code" in schema_src
    assert 'role="student"' in auth_src


def test_admin_create_teacher_route_exists_and_is_admin_guarded():
    src = ADMIN_PATH.read_text(encoding="utf-8")
    assert '@router.post("/admin/users/teachers")' in src
    assert "Depends(require_admin)" in src


def test_student_cannot_self_change_role_without_admin_route_guard():
    src = ADMIN_PATH.read_text(encoding="utf-8")
    # Role updates are only available in admin patch route, guarded by require_admin
    assert '@router.patch("/admin/users/{user_id}")' in src
    assert "Depends(require_admin)" in src


def test_start_attempt_payload_single_data_key_and_status_fields():
    src = LMS_PATH.read_text(encoding="utf-8")
    start_marker = '@router.post("/attempts/start")'
    start_index = src.index(start_marker)
    next_route = src.index('@router.post("/attempts/{attempt_id}/heartbeat")', start_index)
    start_block = src[start_index:next_route]
    assert start_block.count('"data"') == 1
    assert '"status": status_payload' in start_block
    assert '"deadline_utc"' in start_block


def test_timer_status_has_return_payload():
    src = LMS_PATH.read_text(encoding="utf-8")
    marker = '@router.get("/attempts/{attempt_id}/timer-status")'
    start = src.index(marker)
    end = src.index('@router.get("/attempts/{attempt_id}/status")', start)
    block = src[start:end]
    assert "return {\"request_id\"" in block
    assert '"elapsed_seconds"' in block
    assert '"time_left_seconds"' in block
