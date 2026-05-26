#!/usr/bin/env python3
"""Static scan: auth/, routes/, services/, schemas/, models/, *_routes.py, *_core.py
must NOT import from main."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = re.compile(r"^\s*(from\s+main\s+import|import\s+main\b)")

SCAN_DIRS = ["auth", "routes", "services", "schemas", "models"]
SCAN_GLOBS = ["*_routes.py", "*_core.py"]


def _collect_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        dirpath = ROOT / d
        if dirpath.is_dir():
            files.extend(sorted(dirpath.rglob("*.py")))
    for pattern in SCAN_GLOBS:
        files.extend(sorted(ROOT.glob(pattern)))
    return files


def main() -> int:
    violations: list[str] = []
    for path in _collect_files():
        rel = path.relative_to(ROOT)
        for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                violations.append(f"{rel}:{idx}: {line.strip()}")

    if violations:
        print("Reverse import check FAILED:")
        for v in violations:
            print(f"  {v}")
        return 1

    print("Reverse import check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
