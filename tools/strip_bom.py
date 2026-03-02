#!/usr/bin/env python3
"""Strip UTF-8 BOM from Python files or fail in check mode."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

UTF8_BOM = b"\xef\xbb\xbf"
SKIP_DIR_NAMES = {".git", ".venv", "venv", "node_modules", "__pycache__"}


def iter_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            yield root
            continue

        if not root.exists() or not root.is_dir():
            continue

        for path in root.rglob("*.py"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            yield path


def has_bom(path: Path) -> bool:
    return path.read_bytes().startswith(UTF8_BOM)


def strip_bom(path: Path) -> bool:
    content = path.read_bytes()
    if not content.startswith(UTF8_BOM):
        return False

    path.write_bytes(content[len(UTF8_BOM) :])
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recursively scan directories and strip UTF-8 BOM from *.py files. "
            "Defaults to current repository root."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Directories or files to scan (default: current directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not modify files; exit with code 1 when any BOM is detected.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = [Path(p) for p in args.paths]
    fixed_files: list[Path] = []
    bom_files: list[Path] = []

    for file_path in iter_python_files(roots):
        if not has_bom(file_path):
            continue

        bom_files.append(file_path)
        if not args.check and strip_bom(file_path):
            fixed_files.append(file_path)

    if args.check:
        for file_path in bom_files:
            print(file_path.as_posix())
        print(f"Total with BOM: {len(bom_files)}")
        return 1 if bom_files else 0

    for file_path in fixed_files:
        print(file_path.as_posix())

    print(f"Total fixed: {len(fixed_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
