"""Period/week-label utilities shared across delivery domains (pipeline, roster)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional


def week_label_from_date(d: Any) -> str:
    """口径：周一到周日；例如 3/30-4/5 记作 4w1（按该周周四所在月份归属）。"""
    monday_start = d - timedelta(days=d.weekday())
    week_anchor = monday_start + timedelta(days=3)  # Thursday anchor
    target_month = int(week_anchor.month)
    target_year = int(week_anchor.year)
    first_day = datetime(target_year, target_month, 1).date()
    cursor = first_day - timedelta(days=first_day.weekday())
    while int((cursor + timedelta(days=3)).month) != target_month:
        cursor += timedelta(days=7)
    week_no = ((monday_start - cursor).days // 7) + 1
    return f"{target_month}w{week_no}"


def normalize_period_label(period: str) -> str:
    """统一周期标签为 XwY，兼容 4W3 / 4w3 / 4m3w 等写法。"""
    s = str(period or "").strip()
    if not s:
        return ""
    m1 = re.match(r"^\s*(\d{1,2})\s*m\s*(\d{1,2})\s*w\s*$", s, re.IGNORECASE)
    if m1:
        return f"{int(m1.group(1))}w{int(m1.group(2))}"
    m2 = re.match(r"^\s*(\d{1,2})\s*w\s*(\d{1,2})\s*$", s, re.IGNORECASE)
    if m2:
        return f"{int(m2.group(1))}w{int(m2.group(2))}"
    return s


def period_week_bounds(period: str, year: Optional[int] = None) -> Optional[tuple]:
    """按与 week_label_from_date 一致的口径，返回周期对应的周一/周日日期。"""
    s = normalize_period_label(period)
    m = re.match(r"^\s*(\d{1,2})\s*w\s*(\d{1,2})\s*$", s, re.IGNORECASE)
    if not m:
        return None
    target_month = int(m.group(1))
    week_no = int(m.group(2))
    target_year = int(year or datetime.now().year)
    try:
        first_day = datetime(target_year, target_month, 1).date()
    except Exception:
        return None
    cursor = first_day - timedelta(days=first_day.weekday())
    while int((cursor + timedelta(days=3)).month) != target_month:
        cursor += timedelta(days=7)
    monday_start = cursor + timedelta(days=(week_no - 1) * 7)
    sunday_end = monday_start + timedelta(days=6)
    return (monday_start, sunday_end)


def period_sort_key(period: str) -> tuple:
    s = str(period or "").strip()
    if not s:
        return (999, 999, "")
    m1 = re.match(r"^\s*(\d{1,2})\s*m\s*(\d{1,2})\s*w\s*$", s, re.IGNORECASE)
    if m1:
        return (int(m1.group(1)), int(m1.group(2)), s)
    m2 = re.match(r"^\s*(\d{1,2})\s*w\s*(\d{1,2})\s*$", s, re.IGNORECASE)
    if m2:
        return (int(m2.group(1)), int(m2.group(2)), s)
    return (999, 999, s)


def extract_period_month(period: str) -> Optional[int]:
    s = str(period or "").strip()
    m1 = re.match(r"^\s*(\d{1,2})\s*m", s, re.IGNORECASE)
    if m1:
        return int(m1.group(1))
    m2 = re.match(r"^\s*(\d{1,2})\s*w", s, re.IGNORECASE)
    if m2:
        return int(m2.group(1))
    m3 = re.search(r"(\d{1,2})\s*月", s)
    if m3:
        return int(m3.group(1))
    return None
