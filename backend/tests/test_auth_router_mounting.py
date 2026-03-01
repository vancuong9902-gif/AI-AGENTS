from __future__ import annotations

import ast
from pathlib import Path

from fastapi import APIRouter, FastAPI


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


def _load_include_api_routers_function():
    source = MAIN_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    include_fn = None
    router_names: set[str] = set()

    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_include_api_routers":
            include_fn = node
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                if not isinstance(inner.func, ast.Attribute) or inner.func.attr != "include_router":
                    continue
                if inner.args and isinstance(inner.args[0], ast.Name):
                    router_names.add(inner.args[0].id)
            break

    assert include_fn is not None

    # keep only the target function so importing main's other modules is unnecessary
    isolated_module = ast.Module(body=[include_fn], type_ignores=[])
    ast.fix_missing_locations(isolated_module)

    globals_dict: dict[str, object] = {"FastAPI": FastAPI}
    for name in router_names:
        router = APIRouter()
        if name == "auth_router":
            @router.post("/auth/login")
            def _login():
                return {"ok": True}
        globals_dict[name] = router

    exec(compile(isolated_module, filename=str(MAIN_PATH), mode="exec"), globals_dict)
    return globals_dict["_include_api_routers"]


def _has_auth_login_route(app: FastAPI) -> bool:
    return any(getattr(route, "path", None) == "/api/auth/login" for route in app.routes)


def test_auth_endpoint_exists_when_auth_enabled_true():
    include_api_routers = _load_include_api_routers_function()
    app = FastAPI()

    include_api_routers(app, True)

    assert _has_auth_login_route(app)


def test_auth_endpoint_returns_404_when_auth_enabled_false():
    include_api_routers = _load_include_api_routers_function()
    app = FastAPI()

    include_api_routers(app, False)

    assert not _has_auth_login_route(app)
