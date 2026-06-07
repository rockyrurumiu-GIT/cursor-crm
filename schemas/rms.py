"""RMS request/response schemas and status transition constants."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

RECEIVE_STATUSES = frozenset({"pending", "accepted", "rejected"})
DELIVERY_REVIEW_STATUSES = frozenset({"pending", "passed", "failed"})

LEGACY_STATUS_NORMALIZE: dict[str, str] = {
    "screening": "pending_client_screen",
    "interview": "pending_first_interview",
    "offer": "pending_offer",
}

APPLICATION_PROGRESS_TERMINAL = frozenset({
    "internal_screen_failed",
    "client_screen_failed",
    "interview_scheduling_failed",
    "first_interview_failed",
    "second_interview_failed",
    "second_interview_abandoned",
    "final_interview_failed",
    "final_interview_abandoned",
    "offer_dropped",
    "onboarding_lost",
    "hired",
    "rejected",
    "withdrawn",
})

APPLICATION_TERMINAL = APPLICATION_PROGRESS_TERMINAL

ACTIVE_PIPELINE_STATUSES = frozenset({
    "pending_internal_screen",
    "pending_client_screen",
    "scheduling_interview",
    "pending_first_interview",
    "first_interview_passed",
    "second_interview_passed",
    "pending_offer",
    "onboarding",
})

APPLICATION_PROGRESS_STATUSES = frozenset({
    "pending_internal_screen",
    "internal_screen_failed",
    "pending_client_screen",
    "client_screen_failed",
    "scheduling_interview",
    "interview_scheduling_failed",
    "pending_first_interview",
    "first_interview_passed",
    "first_interview_failed",
    "second_interview_passed",
    "second_interview_failed",
    "second_interview_abandoned",
    "final_interview_failed",
    "final_interview_abandoned",
    "pending_offer",
    "offer_dropped",
    "onboarding",
    "onboarding_lost",
    "hired",
})

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending_internal_screen": {"internal_screen_failed", "pending_client_screen"},
    "pending_client_screen": {"client_screen_failed", "scheduling_interview"},
    "scheduling_interview": {"interview_scheduling_failed", "pending_first_interview"},
    "pending_first_interview": {"first_interview_failed", "first_interview_passed"},
    "first_interview_passed": {
        "second_interview_failed",
        "second_interview_passed",
        "second_interview_abandoned",
    },
    "second_interview_passed": {
        "final_interview_failed",
        "pending_offer",
        "final_interview_abandoned",
    },
    "pending_offer": {"offer_dropped", "onboarding"},
    "onboarding": {"onboarding_lost", "hired"},
}

_HIRED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RMS_DATE_RE = _HIRED_AT_RE

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


def normalize_application_status(status: str) -> str:
    s = (status or "").strip()
    if not s:
        return "recommended"
    return LEGACY_STATUS_NORMALIZE.get(s, s)


def utc_date_str() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize_rms_date(value: Any) -> str:
    """Normalize RMS date fields to YYYY-MM-DD for storage/API output."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    head = s[:10]
    if _RMS_DATE_RE.match(head):
        return head
    return s


def validate_hired_at(value: str) -> str:
    from fastapi import HTTPException

    v = (value or "").strip()
    if not v:
        raise HTTPException(status_code=400, detail="已入职状态必须填写入职时间 hired_at")
    if not _HIRED_AT_RE.match(v):
        raise HTTPException(status_code=400, detail="hired_at 格式须为 YYYY-MM-DD")
    return v


def is_pipeline_eligible_application(row: Any) -> bool:
    recv = (getattr(row, "receive_status", None) or "pending").strip()
    dr = (getattr(row, "delivery_review_status", None) or "pending").strip()
    return recv == "accepted" and dr == "passed"


def validate_status_correction_note(note: str) -> str:
    from fastapi import HTTPException

    v = (note or "").strip()
    if len(v) < 2:
        raise HTTPException(status_code=400, detail="状态修正备注至少 2 个字")
    return v


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
    mode: Literal["transition", "correction"] = "transition"
    hired_at: str = ""
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
