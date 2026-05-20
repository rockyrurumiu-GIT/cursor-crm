"""客户拜访记录：序列化与校验。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class VisitBody(BaseModel):
    client_id: int
    week_period: str = ""
    region: str = ""
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
