"""客户拜访记录：序列化与校验。"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


def parse_visit_date(val: str) -> Optional[date]:
    """解析拜访时间字段（YYYY-MM-DD 或常见日期文本）。"""
    s = (val or "").strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def week_label_from_date(d: date) -> str:
    """与交付 pipeline 一致：按该周周四所在月份归属，如 5w3。"""
    monday_start = d - timedelta(days=d.weekday())
    week_anchor = monday_start + timedelta(days=3)
    target_month = int(week_anchor.month)
    target_year = int(week_anchor.year)
    first_day = date(target_year, target_month, 1)
    cursor = first_day - timedelta(days=first_day.weekday())
    while int((cursor + timedelta(days=3)).month) != target_month:
        cursor += timedelta(days=7)
    week_no = ((monday_start - cursor).days // 7) + 1
    return f"{target_month}w{week_no}"


def week_filter_key(d: date) -> str:
    """筛选下拉 value：含年份，避免跨年同周次混淆。"""
    return f"{d.year}-{week_label_from_date(d)}"


def parse_week_filter_key(key: str) -> Tuple[Optional[int], str]:
    s = (key or "").strip()
    m = re.match(r"^(\d{4})-(\d{1,2})[wW](\d{1,2})$", s)
    if m:
        return int(m.group(1)), f"{int(m.group(2))}w{int(m.group(3))}"
    m2 = re.match(r"^(\d{1,2})[wW](\d{1,2})$", s, re.IGNORECASE)
    if m2:
        return None, f"{int(m2.group(1))}w{int(m2.group(2))}"
    return None, ""


def week_bounds_from_label(period: str, year: Optional[int] = None) -> Optional[Tuple[date, date]]:
    m = re.match(r"^\s*(\d{1,2})\s*[wW]\s*(\d{1,2})\s*$", (period or "").strip(), re.IGNORECASE)
    if not m:
        return None
    target_month = int(m.group(1))
    week_no = int(m.group(2))
    target_year = int(year or datetime.now().year)
    try:
        first_day = date(target_year, target_month, 1)
    except ValueError:
        return None
    cursor = first_day - timedelta(days=first_day.weekday())
    while int((cursor + timedelta(days=3)).month) != target_month:
        cursor += timedelta(days=7)
    monday_start = cursor + timedelta(days=(week_no - 1) * 7)
    return monday_start, monday_start + timedelta(days=6)


def week_option_label(week_key: str, year: Optional[int] = None) -> str:
    y, label = parse_week_filter_key(week_key)
    if not label:
        return week_key
    use_year = y if y is not None else year
    m = re.match(r"^(\d+)w(\d+)$", label.lower())
    if not m:
        return week_key
    month, wk = int(m.group(1)), int(m.group(2))
    text = f"{month}月第{wk}周"
    if use_year:
        text = f"{use_year}年{text}"
    bounds = week_bounds_from_label(label, use_year)
    if bounds:
        mon, sun = bounds
        text += f" ({mon.month}/{mon.day}-{sun.month}/{sun.day})"
    return text


def _visit_period_raw(row: Any) -> str:
    """兼容 week_period 为空、日期落在 date 列的旧数据。"""
    wp = str(getattr(row, "week_period", None) or "").strip()
    if wp:
        return wp
    return str(getattr(row, "date", None) or "").strip()


def period_text_to_week_key(raw: str, year_hint: Optional[int] = None) -> str:
    """日期 / 2026-5w2 / 5月第2周 / 2026年5月第2周 → 统一筛选 key。"""
    s = (raw or "").strip()
    if not s:
        return ""
    d = parse_visit_date(s)
    if d:
        return week_filter_key(d)
    y, label = parse_week_filter_key(s)
    if label:
        use_year = y if y is not None else (year_hint or datetime.now().year)
        return f"{use_year}-{label}"
    m = re.match(r"^(?:(\d{4})\s*年)?\s*(\d{1,2})\s*月第\s*(\d{1,2})\s*周", s)
    if m:
        use_year = int(m.group(1)) if m.group(1) else (year_hint or datetime.now().year)
        return f"{use_year}-{int(m.group(2))}w{int(m.group(3))}"
    return ""


def visit_week_filter_key(period_str: str) -> str:
    return period_text_to_week_key(period_str)


def visit_matches_week_filter(period_str: str, filter_week: str) -> bool:
    if not filter_week:
        return True
    got = visit_week_filter_key(period_str)
    if got and got.lower() == filter_week.strip().lower():
        return True
    y, label = parse_week_filter_key(filter_week)
    if not label:
        return False
    d = parse_visit_date(period_str)
    if not d:
        return False
    if y is not None and d.year != y:
        return False
    return week_label_from_date(d).lower() == label.lower()


def collect_visit_week_options(rows: List[Any]) -> List[Dict[str, str]]:
    """从拜访记录汇总按周筛选项，新周在前。"""
    seen: Dict[str, date] = {}
    for r in rows:
        raw = _visit_period_raw(r)
        key = period_text_to_week_key(raw)
        if not key:
            continue
        d = parse_visit_date(raw)
        if not d:
            y, label = parse_week_filter_key(key)
            bounds = week_bounds_from_label(label, y) if label else None
            d = bounds[0] if bounds else date.min
        if key not in seen or d > seen[key]:
            seen[key] = d
    ordered = sorted(seen.items(), key=lambda x: x[1], reverse=True)
    return [{"value": k, "label": week_option_label(k)} for k, _ in ordered]


class VisitBody(BaseModel):
    client_id: int
    week_period: str = ""
    region: str = ""
    city: str = ""
    salesperson: str = ""
    planned_time: str = ""
    way: str = ""
    visit_purpose: str = ""
    target: str = ""
    accompanying: str = ""
    completed: str = ""
    completion_time: str = ""
    duration_minutes: str = ""
    result: str = ""
    summary_formed: str = ""
    visit_summary: str = ""
    next_plan: str = ""
    date: str = ""
    location: str = ""
    content: str = ""


def visit_to_dict(v: Any, client_name: str = "") -> Dict[str, Any]:
    return {
        "id": v.id,
        "client_id": v.client_id,
        "client_name": client_name,
        "week_period": v.week_period or v.date or "",
        "region": v.region or v.location or "",
        "city": getattr(v, "city", None) or "",
        "salesperson": v.salesperson or "",
        "planned_time": v.planned_time or "",
        "way": v.way or "",
        "visit_purpose": v.visit_purpose or v.content or "",
        "target": v.target or "",
        "accompanying": v.accompanying or "",
        "completed": v.completed or "",
        "completion_time": v.completion_time or "",
        "duration_minutes": v.duration_minutes or "",
        "result": v.result or "",
        "summary_formed": v.summary_formed or "",
        "visit_summary": v.visit_summary or "",
        "next_plan": v.next_plan or "",
        "date": v.date or "",
        "location": v.location or "",
        "content": v.content or "",
        "attachment": v.attachment,
        "created_at": v.created_at.isoformat() if getattr(v, "created_at", None) else "",
        "updated_at": v.updated_at.isoformat() if getattr(v, "updated_at", None) else "",
    }


def apply_visit_body(v: Any, body: VisitBody) -> None:
    v.client_id = body.client_id
    v.week_period = body.week_period.strip()
    v.region = body.region.strip()
    v.city = body.city.strip()
    v.salesperson = body.salesperson.strip()
    v.planned_time = body.planned_time.strip()
    v.way = body.way.strip()
    v.visit_purpose = body.visit_purpose.strip()
    v.target = body.target.strip()
    v.accompanying = body.accompanying.strip()
    v.completed = body.completed.strip()
    v.completion_time = body.completion_time.strip()
    v.duration_minutes = body.duration_minutes.strip()
    v.result = body.result.strip()
    v.summary_formed = body.summary_formed.strip()
    v.visit_summary = body.visit_summary.strip()
    v.next_plan = body.next_plan.strip()
    v.date = body.date.strip() or body.week_period.strip()
    v.location = body.location.strip() or body.region.strip()
    v.content = body.content.strip() or body.visit_purpose.strip()
    v.updated_at = datetime.now()
