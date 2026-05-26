#!/usr/bin/env python3
"""Run architecture guardrail scripts."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "check_reverse_imports.py",
    "check_route_permissions.py",
    "check_file_sizes.py",
)


def main() -> int:
    exit_code = 0
    for name in SCRIPTS:
        path = ROOT / "scripts" / name
        print(f"=== {name} ===")
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT),
            check=False,
        )
        print()
        if result.returncode != 0:
            exit_code = result.returncode
    print("Next: ./venv/bin/python -m pytest tests/ -q")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
