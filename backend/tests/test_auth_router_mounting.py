from __future__ import annotations

import ast
from pathlib import Path


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


def _parse_main_module() -> ast.Module:
    return ast.parse(MAIN_PATH.read_text(encoding="utf-8"))


def test_auth_router_is_included_under_api_prefix():
    module = _parse_main_module()

    found_auth_include = False
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "include_router":
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Name) and first_arg.id == "auth_router":
            prefixes = [kw.value.value for kw in node.keywords if kw.arg == "prefix" and isinstance(kw.value, ast.Constant)]
            if "/api" in prefixes:
                found_auth_include = True
                break

    assert found_auth_include


def test_auth_router_mount_is_guarded_by_auth_enabled_flag():
    module = _parse_main_module()

    guarded_include = False
    for node in ast.walk(module):
        if not isinstance(node, ast.If):
            continue
        if not isinstance(node.test, ast.Name) or node.test.id != "auth_enabled":
            continue

        for stmt in node.body:
            if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
                continue
            call = stmt.value
            if not isinstance(call.func, ast.Attribute) or call.func.attr != "include_router":
                continue
            if call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "auth_router":
                guarded_include = True
                break

    assert guarded_include
