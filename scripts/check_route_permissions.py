#!/usr/bin/env python3
"""Static scan: business /api/ routes should use require_permission."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROUTE_DECORATOR = re.compile(
    r'@(?:app|router)\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']'
)
PERM = re.compile(r"require_(?:any_)?permission\s*\(|auth_deps\.require_(?:any_)?permission\s*\(")
AUTH_ONLY = re.compile(r"Depends\s*\(\s*authenticate\s*\)")
CUSTOM_GUARD = re.compile(r"Depends\s*\(\s*_\w+")
ASYNC_DEF = re.compile(r"^\s*async def ")

WHITELIST = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/legacy-bootstrap",
    "/api/me",
    "/api/account/change-password",
}

SCAN_FILES: list[Path] = [ROOT / "main.py"]
SCAN_FILES.extend(sorted(ROOT.glob("*_routes.py")))
routes_dir = ROOT / "routes"
if routes_dir.is_dir():
    SCAN_FILES.extend(sorted(routes_dir.rglob("*.py")))


def _scan_file(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rel = path.relative_to(ROOT)
    missing: list[str] = []
    auth_only: list[str] = []

    for idx, line in enumerate(lines):
        m = ROUTE_DECORATOR.search(line)
        if not m:
            continue
        path_str = m.group(2)
        if not path_str.startswith("/api/"):
            continue
        if path_str in WHITELIST:
            continue

        sig_lines: list[str] = []
        for j in range(idx + 1, min(idx + 40, len(lines))):
            sig_lines.append(lines[j])
            if ASYNC_DEF.search(lines[j]):
                continue
            if sig_lines and sig_lines[-1].rstrip().endswith("):"):
                break

        signature = "\n".join(sig_lines)
        if PERM.search(signature) or CUSTOM_GUARD.search(signature):
            continue
        if AUTH_ONLY.search(signature):
            auth_only.append(f"{rel}:{idx + 1}: {path_str} (Depends(authenticate) only)")
            continue
        missing.append(f"{rel}:{idx + 1}: {path_str} (no require_permission)")

    return missing, auth_only


def main() -> int:
    all_missing: list[str] = []
    all_auth_only: list[str] = []
    for path in SCAN_FILES:
        if not path.is_file():
            continue
        missing, auth_only = _scan_file(path)
        all_missing.extend(missing)
        all_auth_only.extend(auth_only)

    exit_code = 0
    if all_auth_only:
        print("Route permission warnings (authenticate only, no require_permission):")
        for item in all_auth_only:
            print(f"  WARNING {item}")

    if all_missing:
        print("Route permission check FAILED (business /api/ without require_permission):")
        for item in all_missing:
            print(f"  ERROR {item}")
        exit_code = 1

    if exit_code == 0 and not all_auth_only:
        print("Route permission check passed.")
    elif exit_code == 0 and all_auth_only:
        print("Route permission check passed with warnings.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
