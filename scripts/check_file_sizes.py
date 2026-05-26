#!/usr/bin/env python3
"""Warn/error when tracked files grow beyond architecture baselines."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASELINES = {
    "main.py": 7029,
    "templates/base.html": 1596,
    "templates/pages/delivery_detail.html": 4394,
    "templates/pages/delivery_settlement.html": 1140,
    "templates/pages/roster_detail.html": 1503,
}

GROWTH_SLACK = 50
LARGE_PAGE_JS_LINES = 1200

PHASE2_MARKER = ROOT / "reports/architecture/phase-02-settlement-report.md"


def _phase2_complete() -> bool:
    if not PHASE2_MARKER.is_file():
        return False
    return "PASS" in PHASE2_MARKER.read_text(encoding="utf-8")


def _count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def main() -> int:
    strict = _phase2_complete()
    mode = "strict (Phase 2 PASS)" if strict else "pre-Phase-2 (warnings only for governance files)"
    print(f"File size check mode: {mode}")

    errors: list[str] = []
    warnings: list[str] = []

    for rel, baseline in BASELINES.items():
        path = ROOT / rel
        if not path.is_file():
            warnings.append(f"{rel}: missing (baseline {baseline})")
            continue
        count = _count_lines(path)
        limit = baseline + GROWTH_SLACK
        if count > limit:
            msg = f"{rel}: {count} lines (baseline {baseline}, limit {limit})"
            if strict and rel in ("main.py", "templates/pages/delivery_detail.html"):
                errors.append(msg)
            else:
                warnings.append(msg)
        elif count > baseline:
            warnings.append(f"{rel}: {count} lines (baseline {baseline}, within +{GROWTH_SLACK} slack)")

    pages_dir = ROOT / "templates/pages"
    if pages_dir.is_dir():
        baseline_pages = {ROOT / k for k in BASELINES if k.startswith("templates/pages/")}
        for path in sorted(pages_dir.glob("*.html")):
            if path in baseline_pages:
                continue
            count = _count_lines(path)
            if count > LARGE_PAGE_JS_LINES:
                warnings.append(f"{path.relative_to(ROOT)}: {count} lines (> {LARGE_PAGE_JS_LINES})")

    js_pages = ROOT / "static/js/pages"
    if js_pages.is_dir():
        for path in sorted(js_pages.glob("*.js")):
            count = _count_lines(path)
            if count > LARGE_PAGE_JS_LINES:
                warnings.append(f"{path.relative_to(ROOT)}: {count} lines (> {LARGE_PAGE_JS_LINES})")

    if warnings:
        print("File size warnings:")
        for item in warnings:
            print(f"  WARNING {item}")

    if errors:
        print("File size check FAILED:")
        for item in errors:
            print(f"  ERROR {item}")
        return 1

    print("File size check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
