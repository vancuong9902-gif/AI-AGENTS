#!/usr/bin/env python3
"""Strip UTF-8 BOM from Python files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

UTF8_BOM = b"\xef\xbb\xbf"


def iter_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            yield root
            continue

        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if path.is_file():
                yield path


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
            "Defaults to backend/."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["backend"],
        help="Directories or files to scan (default: backend)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = [Path(p) for p in args.paths]
    fixed_files: list[Path] = []

    for file_path in iter_python_files(roots):
        if strip_bom(file_path):
            fixed_files.append(file_path)

    for file_path in fixed_files:
        print(file_path.as_posix())

    print(f"Total fixed: {len(fixed_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
