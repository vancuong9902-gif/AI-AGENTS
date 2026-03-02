from __future__ import annotations

from pathlib import Path

ADMIN_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "admin.py"
AUTH_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "auth.py"
DEPS_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "deps.py"


def test_simple_required_routes_exist():
    auth_src = AUTH_PATH.read_text(encoding="utf-8")
    admin_src = ADMIN_PATH.read_text(encoding="utf-8")

    assert '@router.post("/login")' in auth_src
    assert '@router.post("/admin/create-teacher")' in admin_src
    assert '@router.get("/users")' in admin_src


def test_teacher_creation_and_user_listing_are_admin_guarded():
    src = ADMIN_PATH.read_text(encoding="utf-8")
    assert "Depends(require_admin)" in src


def test_users_endpoint_has_pagination_and_registration_forces_student_role():
    admin_src = ADMIN_PATH.read_text(encoding="utf-8")
    auth_src = AUTH_PATH.read_text(encoding="utf-8")

    assert "limit: int = Query" in admin_src
    assert "offset: int = Query" in admin_src
    assert 'role="student"' in auth_src


def test_role_check_dependency_helper_exists():
    deps_src = DEPS_PATH.read_text(encoding="utf-8")
    assert "def require_roles(*allowed_roles: str):" in deps_src
