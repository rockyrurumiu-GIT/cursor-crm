"""Shared date utilities for delivery subdomains (roster, pipeline, interviews)."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional


def parse_loose_date(raw: str) -> Optional[date]:
    """Parse dates in various loose formats: 2026-04-16, 2026/4/16, 2026年4月16日, etc."""
    s = str(raw or "").strip()
    if not s:
        return None
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s)
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2))
    d = int(m.group(3))
    try:
        return datetime(y, mo, d).date()
    except Exception:
        return None
