"""RMS request/response schemas and status transition constants (Phase 2)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

APPLICATION_TERMINAL = frozenset({"hired", "rejected", "withdrawn"})

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "recommended": {"screening", "rejected", "withdrawn"},
    "screening": {"interview", "rejected", "withdrawn"},
    "interview": {"offer", "rejected", "withdrawn"},
    "offer": {"hired", "rejected", "withdrawn"},
    "hired": set(),
    "rejected": set(),
    "withdrawn": set(),
}

FORBIDDEN_APPLICATION_BODY_KEYS = frozenset({
    "status",
    "client_id",
    "current_stage",
    "last_activity_at",
})

JOB_PRIORITIES = frozenset({"high", "medium", "low"})
JOB_STATUSES = frozenset({"open", "closed", "freeze"})

JOB_WRITABLE_STR_FIELDS = (
    "title",
    "department",
    "location",
    "job_description",
    "requirements",
    "status",
    "priority",
    "salary_cap",
    "years_required",
    "education",
    "overtime_travel",
    "interviewer",
    "note",
)


def reject_forbidden_application_keys(body: dict) -> None:
    from fastapi import HTTPException

    if not isinstance(body, dict):
        return
    bad = sorted(FORBIDDEN_APPLICATION_BODY_KEYS & body.keys())
    if bad:
        raise HTTPException(status_code=400, detail=f"不允许的字段: {', '.join(bad)}")


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int
    candidate_id: int
    resume_id: Optional[int] = None


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: Optional[int] = None
    candidate_id: Optional[int] = None
    resume_id: Optional[int] = None


class ApplicationStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_status: str
    reason: str = ""
    note: str = ""


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int
    title: str = ""
    department: str = ""
    location: str = ""
    headcount: int = 1
    job_description: str = ""
    requirements: str = ""
    status: str = "open"
    priority: str = "medium"
    salary_cap: str = ""
    years_required: str = ""
    education: str = ""
    overtime_travel: str = ""
    interviewer: str = ""
    note: str = ""
    owner_user_id: int
    delivery_owner_user_id: Optional[int] = None
    sales_owner_user_id: Optional[int] = None


class JobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: Optional[int] = None
    title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    headcount: Optional[int] = None
    job_description: Optional[str] = None
    requirements: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    salary_cap: Optional[str] = None
    years_required: Optional[str] = None
    education: Optional[str] = None
    overtime_travel: Optional[str] = None
    interviewer: Optional[str] = None
    note: Optional[str] = None
    owner_user_id: Optional[int] = None


class CandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    phone: str = ""
    email: str = ""
    wechat: str = ""
    current_company: str = ""
    current_title: str = ""
    city: str = ""
    source: str = ""
    tags: str = "[]"


class CandidateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    wechat: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    city: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None
