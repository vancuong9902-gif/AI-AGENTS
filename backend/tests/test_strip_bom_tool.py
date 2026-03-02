from __future__ import annotations

import subprocess
import sys
from pathlib import Path


UTF8_BOM = b"\xef\xbb\xbf"


def run_strip_bom(*args: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "tools" / "strip_bom.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_strip_bom_check_mode_detects_bom(tmp_path: Path) -> None:
    py_file = tmp_path / "sample.py"
    py_file.write_bytes(UTF8_BOM + b"print('hello')\n")

    result = run_strip_bom("--check", str(tmp_path))

    assert result.returncode == 1
    assert py_file.as_posix() in result.stdout
    assert "Total with BOM: 1" in result.stdout
    assert py_file.read_bytes().startswith(UTF8_BOM)


def test_strip_bom_fix_mode_removes_bom(tmp_path: Path) -> None:
    py_file = tmp_path / "sample.py"
    py_file.write_bytes(UTF8_BOM + b"print('hello')\n")

    result = run_strip_bom(str(tmp_path))

    assert result.returncode == 0
    assert py_file.as_posix() in result.stdout
    assert "Total fixed: 1" in result.stdout
    assert py_file.read_bytes() == b"print('hello')\n"

    check_result = run_strip_bom("--check", str(tmp_path))
    assert check_result.returncode == 0
    assert "Total with BOM: 0" in check_result.stdout
