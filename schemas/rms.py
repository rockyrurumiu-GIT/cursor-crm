"""RMS request/response schemas and status transition constants (Phase 2)."""
from __future__ import annotations

from typing import Literal, Optional

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


class DeliveryReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: Literal["passed", "failed"]
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


CANDIDATE_EDUCATION_LEVELS = frozenset(
    {"重本", "统本", "专科", "硕士", "留学生", "民教网", "其他"}
)
CANDIDATE_GENDERS = frozenset({"男", "女"})
CANDIDATE_SOURCES = frozenset(
    {"平台", "Boss", "linkedin", "猎聘", "内推", "挂靠", "外协", "其他"}
)
CANDIDATE_MARITAL_STATUSES = frozenset({"未婚", "已婚"})

CANDIDATE_WRITABLE_STR_FIELDS = (
    "name",
    "phone",
    "email",
    "wechat",
    "email_wechat",
    "age",
    "work_years",
    "current_salary",
    "expected_salary",
    "available_date",
    "education_level",
    "school",
    "major",
    "gender",
    "marital_status",
    "current_company",
    "current_title",
    "city",
    "source",
    "tags",
)


class CandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    phone: str = ""
    email: str = ""
    wechat: str = ""
    email_wechat: str = ""
    age: str = ""
    work_years: str = ""
    target_job_id: Optional[int] = None
    target_client_id: Optional[int] = None
    current_salary: str = ""
    expected_salary: str = ""
    available_date: str = ""
    education_level: str = ""
    school: str = ""
    major: str = ""
    gender: str = ""
    marital_status: str = ""
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
    email_wechat: Optional[str] = None
    age: Optional[str] = None
    work_years: Optional[str] = None
    target_job_id: Optional[int] = None
    target_client_id: Optional[int] = None
    current_salary: Optional[str] = None
    expected_salary: Optional[str] = None
    available_date: Optional[str] = None
    education_level: Optional[str] = None
    school: Optional[str] = None
    major: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    city: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None
